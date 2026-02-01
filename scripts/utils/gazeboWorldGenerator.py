import os
import cv2
import shutil
import json
from utils.fileWriter import FileWriter
from utils.param import globalParam
from utils.maptileUtils import maptile_utiles
from utils.buildingsGenerator import GeoJSONToDAE
from utils.heightMapGenerator import HeightmapGenerator
from utils.utils import ConcatImage
from geopy.distance import geodesic
from geopy.distance import distance
from geopy.point import Point
from multiprocessing import Pool, cpu_count
from PIL import Image
import rasterio


class OrthoGenerator(ConcatImage):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)


    def generate_ortho(self,path: str,zoomlevel,model_name,boundaries)-> None:
        """
        Generate the aerial image of the map.

        Args:
            path (str): Path to metadata.

        Returns:
            None
        """
 
        image_dir = os.path.join(path, str(zoomlevel))
        # Check and create necessary directories
        maptile_utiles.dir_check(os.path.join(globalParam.GAZEBO_MODEL_PATH, model_name, 'textures'),remove_existing=True)
        maptile_utiles.dir_check(os.path.join(globalParam.TEMPORARY_SATELLITE_IMAGE, model_name),remove_existing=True)
        bound_array = boundaries.split(',')
        tile_boundaries = maptile_utiles.get_max_tilenumber(bound_array,zoomlevel)
        image_dir_list = self.get_x_tile_directories(image_dir,tile_boundaries)


        temp_output_dir = os.path.join(globalParam.TEMPORARY_SATELLITE_IMAGE, model_name)
        args_list = [
            (self, dir_name, image_dir, tile_boundaries, temp_output_dir)
            for dir_name in image_dir_list
        ]
        #  Multiprocessing call
        with Pool(processes=cpu_count()) as pool:
            pool.map(OrthoGenerator._run_instance_method, args_list)

        image_list = sorted([
            os.path.join(temp_output_dir, img)
            for img in os.listdir(temp_output_dir) if img.endswith('.png')
        ])            
        images = [cv2.imread(path) for path in image_list]
        filtered_images = [images[0]]

        for img in images[1:]:
            if OrthoGenerator.are_dimensions_equal(filtered_images[-1], img):
                filtered_images.append(img)
        stitched_image = cv2.hconcat(filtered_images)

        # Save the stitched image
        compression_params = [cv2.IMWRITE_PNG_COMPRESSION, 9]
        cv2.imwrite(os.path.join(globalParam.GAZEBO_MODEL_PATH, model_name, 'textures', model_name+'_aerial.png'), stitched_image, compression_params)



class GazeboTerrianGenerator(HeightmapGenerator,OrthoGenerator):
    def __init__(self,tile_path:str,include_buildings: bool,**kwargs):
        super().__init__(**kwargs)
        self.tile_path = tile_path
        self.include_buildings = include_buildings
        with open(os.path.join(self.tile_path, 'metadata.json')) as f:
            data = json.load(f)
            self.boundaries = data["bounds"]
            self.launch_location = data["launch_location"]
            self.zoom_level = data["zoom_level"]
        self.model_name = os.path.basename(self.tile_path)


    def get_origin_height(self)-> float:
        """
        Get the height at the centre of the heightmap data.

        Args:
            height_data: Elevation data.
            resolution (int): Resolution of the heightmap.

        Returns:
            float: Origin height.
        """

        origin_cord = self.get_true_origin()
        return origin_cord["altitude"]
    


    def get_true_origin(self)-> list:
        """
            Get the true origin of the map based on the boundaries and zoom level.
            Args:
                None
            Returns:
                dict: A dictionary containing latitude, longitude, and altitude of the origin.
        """
    
        bound_array = self.boundaries.split(',')
        boundaries = maptile_utiles.get_true_boundaries(bound_array,self.zoom_level)

        sw = boundaries["southwest"]
        se = boundaries["southeast"]
        ne = boundaries["northeast"]
        origin_lon,origin_lat = float((se[1]+sw[1])/2),float((sw[0]+ne[0])/2) 
        print("True origin:",origin_lat," ",origin_lon)
        return {
            "latitude": origin_lat,
            "longitude": origin_lon,
            "altitude": HeightmapGenerator.get_amsl(origin_lat, origin_lon)
        }

    def get_launch_location(self) -> list:
        """
        Get the launch location from the metadata.

        Returns:
            list: A list containing latitude and longitude of the launch location.
        """
        location_array = self.launch_location.split(',')

        return {
            "latitude": float(location_array[1]),
            "longitude": float(location_array[0]),
            "altitude": HeightmapGenerator.get_amsl(float(location_array[1]), float(location_array[0]))
            }

    def gen_sdf(self, size_x: float, size_y: float, size_z: float, pose_x: float, pose_y: float, pose_z: float, include_buildings : bool) -> None:
        """
        Generate the SDF file for the world.

        Args:
            metadata_path (str): Path to metadata.
            size_x (float): Size in x-direction.
            size_y (float): Size in y-direction.
            size_z (float): Size in z-direction.
            pose_x (float): Pose in x-direction.
            pose_y (float): Pose in y-direction.
            pose_z (float): Pose in z-direction.

        Returns:
            None
        """

        template = FileWriter.read_template(os.path.join(globalParam.TEMPLATE_DIR_PATH ,'sdf_temp.txt'))
        FileWriter.write_sdf_file(template, self.model_name, size_x, size_y, size_z,pose_x,pose_y,pose_z, os.path.join(globalParam.GAZEBO_MODEL_PATH, self.model_name),include_buildings)

    def gen_config(self) -> None:
        """
        Generate the configuration file for the model.

        Args:
            metadata_path (str): Path to metadata.

        Returns:
            None
        """
        template = FileWriter.read_template(os.path.join(globalParam.TEMPLATE_DIR_PATH ,'config_temp.txt'))
        FileWriter.write_config_file(template, self.model_name, os.path.join(globalParam.GAZEBO_MODEL_PATH, self.model_name))
    
    def gen_world(self) -> None:
        """
        Generate the gazebo world file.

        Args:

        Returns:
            None
        """

        template = FileWriter.read_template(os.path.join(globalParam.TEMPLATE_DIR_PATH ,'gazebo_world.txt'))
        launch_cord = self.get_launch_location()
        helipad_exist = os.path.exists(os.path.join(globalParam.GAZEBO_MODEL_PATH, 'helipad'))
        FileWriter.write_world_file(template, self.model_name,launch_cord["latitude"],launch_cord["longitude"],os.path.join(globalParam.GAZEBO_MODEL_PATH, self.model_name),launch_cord["altitude"],helipad_exist)
        FileWriter.write_world_file(template, self.model_name,launch_cord["latitude"],launch_cord["longitude"],globalParam.GAZEBO_WORLD_PATH,launch_cord["altitude"],helipad_exist)

    def get_launch_pixelcord(self, south_west_bound, north_east_bound, width, height, launch_location):
        """
        Calculate pixel coordinates of launch location within heightmap.
        
        Args:
            south_west_bound: Southwest boundary coordinates
            north_east_bound: Northeast boundary coordinates  
            width: Width of heightmap
            height: Height of heightmap
            launch_location: Launch location coordinates
            
        Returns:
            tuple: (px, py) pixel coordinates
        """
        # Extract min/max coordinates
        lat_min = south_west_bound[0]
        lat_max = north_east_bound[0]
        lon_min = south_west_bound[1]
        lon_max = north_east_bound[1]
        
        # Calculate pixel coordinates
        px = int((launch_location["longitude"] - lon_min) / (lon_max - lon_min) * width)
        py = int((lat_max - launch_location["latitude"]) / (lat_max - lat_min) * height)
        return px, py
    
    def get_offset(self, origin, coord):
        """
        Calculate the horizontal offset in meters between origin and target coordinates.
        Frame of reference is ENU        
        Args:
            origin (dict): Origin coordinates with 'latitude' and 'longitude' keys
            coord (dict): Target coordinates with 'latitude' and 'longitude' keys
            
        Returns:
            tuple: (pose_x, pose_y) offset in meters
            pose_x: 
            pose_y: 
        """
        # Create Point objects for geopy calculations
        origin_point = Point(origin["latitude"], origin["longitude"])
        
        # Calculate X offset (East-West distance)
        # Use the same latitude but different longitude
        coord_point_x = Point(origin["latitude"], coord["longitude"])
        pose_x = geodesic(origin_point, coord_point_x).meters
        
        # Apply correct sign based on longitude difference
        if coord["longitude"] > origin["longitude"]:
            pose_x = -pose_x 
            
        # Calculate Y offset (North-South distance)  
        # Use the same longitude but different latitude
        coord_point_y = Point(coord["latitude"], origin["longitude"])
        pose_y = geodesic(origin_point, coord_point_y).meters
        
        # Apply correct sign based on latitude difference
        if coord["latitude"] > origin["latitude"]:
            pose_y = -pose_y  
            
        return round(pose_x, 2), round(pose_y, 2)  

    def get_world_dimensions(self):
        """ 
        Get the dimensions of the world based on the heightmap.

        Offset the origin height by 3% of the launch height to avoid collision with the ground.

        Args:
            None
        Returns:
            tuple: A tuple containing size_x, size_y, size_z, and pose_z.
        """
        bound_array = self.boundaries.split(',')
        true_boundaries = maptile_utiles.get_true_boundaries(bound_array, self.zoom_level)
        
        # Calculate map dimensions
        sw = true_boundaries["southwest"]
        se = true_boundaries["southeast"]
        ne = true_boundaries["northeast"]

        self.size_x = round(geodesic(sw, se).m, 2)  
        self.size_y = round(geodesic(se, ne).m, 2)  
        self.size_z = round(self.max_height - self.min_height,2)
        origin_coord = self.get_true_origin()
        launch_location = self.get_launch_location()
        pose_x,pose_y = self.get_offset(origin_coord,launch_location)
        launch_px, launch_py = self.get_launch_pixelcord(
            true_boundaries["southwest"], 
            true_boundaries["northeast"], 
            self.heightmap.size[0], 
            self.heightmap.size[1],
            launch_location
        )

        # Calculate launch height and pose offset
        launch_height = self.heightmap.getpixel((launch_px, launch_py)) * self.size_z / 255
        pose_z = round(-1 * (launch_height + 0.03 * launch_height), 2)  

        return self.size_x,self.size_y,self.size_z,pose_x,pose_y,pose_z

    def generate_gazebo_world(self):
        """
            Generate the gazebo world along with world files.
        """

        print("Map tiles directory being used : ",self.tile_path)
        if os.path.isfile(os.path.join(self.tile_path, 'metadata.json')) and self.tile_path != '':
            self.generate_ortho(self.tile_path,self.zoom_level,self.model_name,self.boundaries)
            print("Satellite image generated successfully")
            self.generate_rgb_heightmap(self.tile_path,self.boundaries,self.zoom_level)
            (size_x,size_y,size_z,pose_x,posey,posez) = self.get_world_dimensions()
            if self.include_buildings:
                origin_coord = self.get_true_origin()
                print("Starting building data download...")
                street_map = os.path.join(globalParam.GAZEBO_MODEL_PATH, self.model_name, 'buildings.geojson')
                output_dae_file = os.path.join(globalParam.GAZEBO_MODEL_PATH, self.model_name, 'textures/buildings.dae')
                true_boundaries = maptile_utiles.get_true_boundaries(self.boundaries.split(','), self.zoom_level)
                geojson_to_dae = GeoJSONToDAE(street_map, output_dae_file)
                geojson_to_dae.run(origin_coord,size_z,posez,self.heightmap, true_boundaries)
                print("Building models generated successfully")
            # Generate SDF files for the world
            self.gen_config()
            self.gen_sdf(size_x,size_y,size_z,pose_x,posey,posez,self.include_buildings)
            maptile_utiles.dir_check(globalParam.GAZEBO_WORLD_PATH)
            self.gen_world()
            print("Generate gazebo model files are save to : ",os.path.join(globalParam.GAZEBO_MODEL_PATH,os.path.basename(self.tile_path)))
            print("Generate gazebo world file are save to : ",globalParam.GAZEBO_WORLD_PATH)
            print("Gazebo world files generated successfully")

            shutil.rmtree(globalParam.TEMP_PATH)
