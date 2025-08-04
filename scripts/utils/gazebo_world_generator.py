import os
import cv2
import shutil
import json
import numpy as np
from utils.file_writer import FileWriter
from utils.param import globalParam
from utils.maptile_utils import maptile_utiles

from geopy.distance import geodesic
from geopy.distance import distance
from geopy.point import Point
from multiprocessing import Pool, cpu_count
from PIL import Image
import math



class ConcatImage:
    def __init__(self,**kwargs):
        super().__init__(**kwargs)

    def get_x_tile_directories(self, image_dir: str, tile_boundaries: dict) -> list:
        """
        Get a numerically sorted list of X-tile directories within tile boundary limits.

        Args:
            image_dir (str): Path to the zoom level directory containing X-tile directories.
            tile_boundaries (dict): Dictionary of tile coordinate bounds.

        Returns:
            list: Sorted list of valid X-tile directory names (as strings).
        """
        # List only directory names that are numeric (tile x)
        dir_list = [d for d in os.listdir(image_dir) if d.isdigit()]

        min_x = min(tile_boundaries["southwest"][0], tile_boundaries["southeast"][0])
        max_x = max(tile_boundaries["southwest"][0], tile_boundaries["southeast"][0])

        # Filter and sort X directories
        x_dirs = sorted([d for d in dir_list if min_x <= int(d) <= max_x], key=lambda x: int(x))

        return x_dirs
       
    def process_column_image(self, dir_name, image_dir, tile_boundaries, temp_output_dir):
        image_list = []
        max_y = max(tile_boundaries["northwest"][1], tile_boundaries["southwest"][1])
        min_y = min(tile_boundaries["northwest"][1], tile_boundaries["southwest"][1])

        dir_path = os.path.join(image_dir, dir_name)
        for image in os.listdir(dir_path):
            tile_num = int(image.split('.')[0])
            if min_y <= tile_num <= max_y:
                image_list.append(os.path.join(dir_path, image))

        image_list.sort()
        images = [cv2.imread(path) for path in image_list if os.path.exists(path)]
        if images:
            output_file = os.path.join(temp_output_dir, dir_name + '.png')
            cv2.imwrite(output_file, cv2.vconcat(images))

    @staticmethod
    def _run_instance_method(args : tuple) -> None:
        """
        Run an instance method with the provided arguments.
        Args:
            args (tuple): A tuple containing the instance and its method arguments.
        Returns:
            None
        """
        instance, dir_name, image_dir, tile_boundaries, temp_output_dir = args
        instance.process_column_image(dir_name, image_dir, tile_boundaries, temp_output_dir)
    
    @staticmethod
    def are_dimensions_equal(img1, img2) -> bool:
        """
        Check if dimensions of two images are equal.

        Args:
            img1: First image.
            img2: Second image.

        Returns:
            bool: True if dimensions are equal, False otherwise.
        """ 
        return img1.shape[:2] == img2.shape[:2]

class HeightmapGenerator(ConcatImage):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.heightmap = None
        self.max_height = self.min_height = 0
        self.size_x=self.size_y=self.size_z=0


    def get_dem_px_bounds(self,true_boundaries,tile_boundaries,height,width):
        crop_px_cord = {}
        # check if tile exist
        lat_max = tile_boundaries["northeast"][0]
        lat_min = tile_boundaries["southwest"][0]
        lon_max = tile_boundaries["northeast"][1]
        lon_min = tile_boundaries["southwest"][1]

        for coord_name in true_boundaries.keys():
            lat, lon = true_boundaries[coord_name]
            # from boundaries and the desiderd lat long get the pixel coordinates
            px = int((lon - lon_min) / (lon_max - lon_min) * width)
            py = int((lat_max - lat) / (lat_max - lat_min) * height)
            crop_px_cord[coord_name] = (px, py)
        return crop_px_cord
        

        
    def get_amsl(self, lat: float, lon: float):
        """
        Get the height above mean sea level (AMSL) for a given latitude and longitude.
        Args:
            lat (float): Latitude in degrees.
            lon (float): Longitude in degrees.
        Returns:
            float: Height above mean sea level in meters.
        """
        tile_x,tile_y = maptile_utiles.lat_lon_to_tile(lat, lon,globalParam.DEM_RESOLUTION)
        boundaries = maptile_utiles.get_tile_bounds(tile_x, tile_y, globalParam.DEM_RESOLUTION)
        # check if tile exist
        lat_max = boundaries["northeast"][0]
        lat_min = boundaries["southwest"][0]
        lon_max = boundaries["northeast"][1]
        lon_min = boundaries["southwest"][1]
        dem_tile_path = os.path.join(globalParam.DEM_PATH, str(globalParam.DEM_RESOLUTION), str(tile_x), str(tile_y)+'.png')
        if os.path.isfile(dem_tile_path) == True:
            # read the image from the tile its a gbr image format
            dem_img = cv2.imread(dem_tile_path)
            #get the size of the image
            height,width = dem_img.shape[:2]
            # from boundaries and the desiderd lat long get the pixel coordinates
            px = int((lon - lon_min) / (lon_max - lon_min) * width)
            py = int((lat_max - lat) / (lat_max - lat_min) * height)
            # from pixel read the image and get the height
            b,g,r = dem_img[py,px]  
            b,g,r = float(b), float(g), float(r)
            # convert the pixel value to height 
            # reference : https://docs.mapbox.com/data/tilesets/reference/mapbox-terrain-dem-v1/
            height = ((r * 256 * 256 + g * 256 + b) * 0.1) - 10000
            return height

        else :
            # raise an error and kill the program

            print("Tile not found",tile_x,tile_y,globalParam.DEM_RESOLUTION,lat,lon)
            return None

    

    def generate_rgb_heightmap(self,model_path,boundaries,zoomlevel) -> list:

        #get the true boundaries as there is a padding non uniform padding added 
        bound_array = boundaries.split(',')
        tile_number_boundaries = maptile_utiles.get_max_tilenumber(bound_array,globalParam.DEM_RESOLUTION)
        image_dir = os.path.join(globalParam.DEM_PATH, str(globalParam.DEM_RESOLUTION))
        image_dir_list = self.get_x_tile_directories(image_dir,tile_number_boundaries)

        temp_output_dir = os.path.join(globalParam.TEMP_PATH, 'heightmap')

        maptile_utiles.dir_check(temp_output_dir,remove_existing=True)

        args_list = [
            (self, dir_name, image_dir, tile_number_boundaries, temp_output_dir)
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
            if ConcatImage.are_dimensions_equal(filtered_images[-1], img):
                filtered_images.append(img)
        stitched_image = cv2.hconcat(filtered_images)
        
        cv2.imwrite(os.path.join(temp_output_dir, 'height_map.png'),stitched_image)

        true_boundaries = maptile_utiles.get_true_boundaries(bound_array,zoomlevel)
        tile_boundaries = maptile_utiles.get_true_boundaries(bound_array,globalParam.DEM_RESOLUTION)

        height,width = stitched_image.shape[:2]
        crop_px_cord = self.get_dem_px_bounds(true_boundaries,tile_boundaries,height,width)
        # Crop the image based on the true boundaries needed
        cropped_image = self.crop_dem_image(crop_px_cord,stitched_image) 
        height,width = cropped_image.shape[:2]

        # Convert to float to avoid overflow during calculation
        cropped_image_float = cropped_image.astype(np.float32)
        # Calculate height map - changed to use float operations
        height_map = ((cropped_image_float[:, :, 2] * 256 * 256 + cropped_image_float[:, :, 1] * 256 + cropped_image_float[:, :, 0]) * 0.1) - 10000
        self.max_height = np.max(height_map)
        self.min_height = np.min(height_map)

        height_img_normalized = ((height_map - np.min(height_map)) / (np.max(height_map) - np.min(height_map)) * 255).astype(np.uint8)

        def get_nearest_map_size(height,width):
            value = max(height, width)
            n = math.log2(value - 1)
            # Get floor and ceil values of n
            n_ceil = int(math.ceil(n))

            size_upper = (2 ** n_ceil) + 1

            return size_upper
        
        size = get_nearest_map_size(height,width)
        resized_map  = cv2.resize(height_img_normalized, (size,size), interpolation=cv2.INTER_LINEAR)

        model = os.path.basename(model_path)

        # Convert OpenCV image to PIL Image and save as TIFF
        self.heightmap = Image.fromarray(resized_map, mode='L')  # 'L' for 8-bit grayscale
        self.heightmap.save(os.path.join(globalParam.GAZEBO_WORLD_PATH, model, 'textures', model+'_height_map.tif'), format="TIFF")



    def crop_dem_image(self,px_bound,height_map):
        cropped_image = height_map[px_bound["northwest"][1]:px_bound["southeast"][1], 
                                       px_bound["southwest"][0]:px_bound["northeast"][0]]
        return cropped_image


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
        maptile_utiles.dir_check(os.path.join(globalParam.GAZEBO_WORLD_PATH, model_name, 'textures'),remove_existing=True)
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
        cv2.imwrite(os.path.join(globalParam.GAZEBO_WORLD_PATH, model_name, 'textures', model_name+'_aerial.png'), stitched_image, compression_params)



class GazeboTerrianGenerator(HeightmapGenerator,OrthoGenerator):
    def __init__(self,tile_path:str,**kwargs):
        super().__init__(**kwargs)
        self.tile_path = tile_path
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
            "altitude": self.get_amsl(origin_lat, origin_lon)
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
            "altitude": self.get_amsl(float(location_array[1]), float(location_array[0]))
            }

    def gen_sdf(self, size_x: float, size_y: float, size_z: float, pose_x: float, pose_y: float, pose_z: float) -> None:
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
        FileWriter.write_sdf_file(template, self.model_name, size_x, size_y, size_z,pose_x,pose_y,pose_z, os.path.join(globalParam.GAZEBO_MODEL_PATH, self.model_name))

    def gen_config(self) -> None:
        """
        Generate the configuration file for the model.

        Args:
            metadata_path (str): Path to metadata.

        Returns:
            None
        """
        template = FileWriter.read_template(os.path.join(globalParam.TEMPLATE_DIR_PATH ,'config_temp.txt'))
        FileWriter.write_config_file(template, self.model_name, os.path.join(globalParam.GAZEBO_WORLD_PATH, self.model_name))
    
    def gen_world(self) -> None:
        """
        Generate the gazebo world file.

        Args:

        Returns:
            None
        """

        template = FileWriter.read_template(os.path.join(globalParam.TEMPLATE_DIR_PATH ,'gazebo_world.txt'))
        launch_cord = self.get_launch_location()
        FileWriter.write_world_file(template, self.model_name,launch_cord["latitude"],launch_cord["longitude"],os.path.join(globalParam.GAZEBO_MODEL_PATH, self.model_name),launch_cord["altitude"])
        FileWriter.write_world_file(template, self.model_name,launch_cord["latitude"],launch_cord["longitude"],globalParam.GAZEBO_WORLD_PATH,launch_cord["altitude"])

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

            # Generate SDF files for the world
            self.gen_config()
            self.gen_sdf(size_x,size_y,size_z,pose_x,posey,posez)
            self.gen_world()
            print("Generate gazebo world files are save to : ",os.path.join(globalParam.GAZEBO_MODEL_PATH,os.path.basename(self.tile_path)))
            print("Gazebo world files generated successfully")

            shutil.rmtree(globalParam.TEMP_PATH)
