# Import necessary libraries
import os, cv2, shutil
import json
import numpy as np
from utils.file_writer import FileWriter
import mercantile
from utils.param import globalParam

from geopy.distance import geodesic
from geopy.distance import distance
from geopy.point import Point



class maptile_utiles:

    
    @staticmethod
    def get_tile_bounds(x, y, zoom):
        """
        Get the latitude/longitude bounds of a tile using the mercantile library.
        Parameters:
        - x (int): Tile number in X direction.
        - y (int): Tile number in Y direction.
        - zoom (int): Zoom level.
        Returns:
        - dict: A dictionary with 'north', 'south', 'east', 'west' latitude/longitude boundaries.
        """
        # Get the bounds of the tile
        bounds = mercantile.bounds(x, y, zoom)

        return {
            "southwest": (bounds.south, bounds.west),   # Southwest corner
            "southeast": (bounds.south, bounds.east),  # Southeast corner
            "northwest": (bounds.north, bounds.west),  # Northwest corner
            "northeast": (bounds.north, bounds.east)  # Northeast corner
        }
    
    @staticmethod
    def get_max_tilenumber(bound_array,zoom): # take zoom level as fundtion param
        '''
        get the squared tile number.
        '''

        sw = (float(bound_array[1]), float(bound_array[0]))
        nw = (float(bound_array[3]), float(bound_array[0]))
        ne = (float(bound_array[3]), float(bound_array[2]))
        se = (float(bound_array[1]), float(bound_array[2]))
        

        sw_tile_x,sw_tile_y = maptile_utiles.lat_lon_to_tile(sw[0],sw[1],zoom)
        nw_tile_x,nw_tile_y = maptile_utiles.lat_lon_to_tile(nw[0],nw[1],zoom)
        ne_tile_x,ne_tile_y = maptile_utiles.lat_lon_to_tile(ne[0],ne[1],zoom)
        se_tile_x,se_tile_y = maptile_utiles.lat_lon_to_tile(se[0],se[1],zoom)


        height,width = abs(nw_tile_x - ne_tile_x), abs(sw_tile_y-nw_tile_y)
        if height != width:
            max_x_tile = nw_tile_x + min(height,width)
            max_y_tile = nw_tile_y + min(height,width)

            return{ 
                    "southwest": (sw_tile_x, max_y_tile),
                    "southeast": (max_x_tile, se_tile_y ),
                    "northwest": (nw_tile_x,nw_tile_y),  
                    "northeast": (max_x_tile, nw_tile_y)
                }
        
        return{ 
                "southwest": (sw_tile_x, sw_tile_y),
                "southeast": (se_tile_x, se_tile_y ),
                "northwest": (nw_tile_x,nw_tile_y),  
                "northeast": (ne_tile_x, nw_tile_y)
                }
    
    @staticmethod
    def get_true_boundaries(bound_array : str,zoom):
        '''
        Returns the lat log of the boundaries
        
        '''
        boundaries  = maptile_utiles.get_max_tilenumber(bound_array,zoom)
        true_sw     = maptile_utiles.get_tile_bounds(boundaries["southwest"][0],boundaries["southwest"][1],zoom)["southwest"]
        true_se     = maptile_utiles.get_tile_bounds(boundaries["southeast"][0],boundaries["southeast"][1],zoom)["southeast"]
        true_nw     = maptile_utiles.get_tile_bounds(boundaries["northwest"][0],boundaries["northwest"][1],zoom)["northwest"]
        true_ne     = maptile_utiles.get_tile_bounds(boundaries["northeast"][0],boundaries["northeast"][1],zoom)["northeast"]
        

        return {
            "southwest": true_sw,  
            "southeast": true_se,  
            "northwest": true_nw,  
            "northeast": true_ne        
        }



    @staticmethod
    def lat_lon_to_tile( lat: float, lon: float, zoom: int):
        """
        Converts latitude and longitude to tile numbers at a given zoom level using mercantile.
        Parameters:
        - lat (float): Latitude in degrees.
        - lon (float): Longitude in degrees.
        - zoom (int): Zoom level.
        Returns:
        - (int, int): Tile x and y numbers.
        """
        # Clamp latitude for Web Mercator projection bounds
        lat = max(min(lat, 85.0511), -85.0511)
        tile = mercantile.tile(lon, lat, zoom)
        return tile.x, tile.y
    
class orthoGenerator:

    def __init__(self,path : str):
        self.metadata_path = path
        with open(os.path.join(self.metadata_path, 'metadata.json')) as f:
            data = json.load(f)
            self.boundaries = data["bounds"]
            self.zoomlevel = data["zoom_level"]
        self.model_name = os.path.basename(self.metadata_path)

    def generate_height_image(self,height_data ,resolution : int) -> None:
        """
        Generate the grey scale height image.

        Args:
            height_data: Elevation data.
            resolution (int): Resolution of the heightmap.

        Returns:
            None

        Resize the image to 1025x1025 or size of height map image should be a square with dimensions of 2^n+1 i.e,(3,3)(5,5)(9,9)...(513,513)(1025,1025)
        ref:https://github.com/AS4SR/general_info/wiki/Creating-Heightmaps-for-Gazebo

        """

        # Normalize elevation data to generate terrain height map
        normalized_array = ((height_data - np.min(height_data)) / (np.max(height_data) - np.min(height_data)) * 255).astype(np.uint8)
        # Reshape the array to a 2D image
        image = normalized_array.reshape((resolution, resolution))


        resized_image = cv2.resize(image, (1025, 1025), interpolation=cv2.INTER_LINEAR)
        blur = cv2.GaussianBlur(resized_image, (1, 1), 0)

        flipped_img = cv2.flip(blur, 0)
        model =os.path.basename(self.metadata_path)
       # Save the height map image
        cv2.imwrite(os.path.join(globalParam.GAZEBO_WORLD_PATH, model, 'textures', model+'_height_map.png'), flipped_img)

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
    



    def gen_sdf(self, size_x :int, size_y :int, size_z :int, pose_z :int) -> None:
        """
        Generate the SDF file for the world.

        Args:
            metadata_path (str): Path to metadata.
            size_x (int): Size in x-direction.
            size_y (int): Size in y-direction.
            size_z (int): Size in z-direction.
            pose_z (int): Pose in z-direction.

        Returns:
            None
        """

        template = FileWriter.read_template(os.path.join(globalParam.TEMPLATE_DIR_PATH ,'sdf_temp.txt'))
        FileWriter.write_sdf_file(template, self.model_name, size_x, size_y, size_z, pose_z, os.path.join(globalParam.GAZEBO_WORLD_PATH, self.model_name))

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

    @staticmethod
    def dir_check(path: str) -> None:
        """
        Check directory existence and create if not exists.

        Args:
            path (str): Path to directory.

        Returns:
            None
        """

        if not os.path.exists(path):
            os.makedirs(path)
        else:
            shutil.rmtree(path)
            os.makedirs(path)


    def get_x_image_dirlist(self, image_dir: str, tile_boundaries: dict) -> list:
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
       
            

    def generate_ortho(self,path: str)-> None:
        """
        Generate the aerial image of the map.

        Args:
            path (str): Path to metadata.

        Returns:
            None
        """
 
        image_dir = os.path.join(path, str(self.zoomlevel))
        
        # Check and create necessary directories
        orthoGenerator.dir_check(os.path.join(globalParam.GAZEBO_WORLD_PATH, self.model_name, 'textures'))
        orthoGenerator.dir_check(os.path.join(globalParam.TEMPORARY_SATELLITE_IMAGE, self.model_name))
        bound_array = self.boundaries.split(',')
        tile_boundaries = maptile_utiles.get_max_tilenumber(bound_array,self.zoomlevel)
        image_dir_list = self.get_x_image_dirlist(image_dir,tile_boundaries)
        # Generate and concatenate images vertically
        for dir in image_dir_list:
            image_list = []
            max_y = max(tile_boundaries["northwest"][1], tile_boundaries["southwest"][1])
            min_y = min(tile_boundaries["northwest"][1], tile_boundaries["southwest"][1])

            for image in os.listdir(os.path.join(image_dir, dir)):
                tile_num = int(image.split('.')[0])
                if  min_y <= tile_num <= max_y:
                    image_list.append(os.path.join(image_dir, dir, image))
            
            image_list.sort()            
            images = [cv2.imread(path) for path in image_list]
            cv2.imwrite(os.path.join(globalParam.TEMPORARY_SATELLITE_IMAGE, self.model_name, dir+'.png'), cv2.vconcat(images))
        # Concatenate images horizontally
        image_list = []
        for image in os.listdir((os.path.join(globalParam.TEMPORARY_SATELLITE_IMAGE, self.model_name))):
            image_list.append(os.path.join(globalParam.TEMPORARY_SATELLITE_IMAGE, self.model_name, image))
            image_list.sort()
        images = [cv2.imread(path) for path in image_list]
        filtered_images = [images[0]]
        for img in images[1:]:
            if orthoGenerator.are_dimensions_equal(filtered_images[-1], img):
                filtered_images.append(img)
        stitched_image = cv2.hconcat(filtered_images)

        # Save the stitched image
        compression_params = [cv2.IMWRITE_PNG_COMPRESSION, 9]
        print(os.path.join(globalParam.GAZEBO_WORLD_PATH, self.model_name, 'textures', self.model_name+'_aerial.png'))
        cv2.imwrite(os.path.join(globalParam.GAZEBO_WORLD_PATH, self.model_name, 'textures', self.model_name+'_aerial.png'), stitched_image, compression_params)


    def get_true_origin(self):
        pass


    def gen_terrain(self)-> list: 
        pass
    
  

class heightmapgenerator(orthoGenerator):
    def __init__(self,path : str):
        super().__init__(path)
        print("using dem class")


    def get_amsl(self, lat: float, lon: float):
        """
        Get the height above mean sea level (AMSL) for a given latitude and longitude.
        Args:
            lat (float): Latitude in degrees.
            lox,y n (float): Longitude in degrees.
        Returns:
            float: Height above mean sea level in meters.
        """
        # Assuming self.dem_instance is an instance of a DEM class that has a getAMSL method
        tile_x,tile_y = maptile_utiles.lat_lon_to_tile(lat, lon,globalParam.HEIGHTMAP_RESOLUTION)
        
        boundaries = maptile_utiles.get_tile_bounds(tile_x, tile_y, globalParam.HEIGHTMAP_RESOLUTION)
        # check if tile exist
        lat_max = boundaries["northeast"][0]
        lat_min = boundaries["southwest"][0]
        lon_max = boundaries["northeast"][1]
        lon_min = boundaries["southwest"][1]
        dem_tile_path = os.path.join(globalParam.DEM_PATH, str(globalParam.HEIGHTMAP_RESOLUTION), str(tile_x), str(tile_y)+'.png')
        if os.path.isfile(dem_tile_path) == True:
            # read the image from the tile
            dem_img = cv2.imread(dem_tile_path)
            #get the size of the image
            height,width = dem_img.shape[:2]
            # from boundaries and the desiderd lat long get the pixel coordinates
            px = (lon - lon_min) / (lon_max - lon_min) * width
            py = (lat_max - lat) / (lat_max - lat_min) * height
            # from pixel read the image and get the height
            r,g,b = dem_img[int(py), int(px)]  
            r, g, b = int(r), int(g), int(b)

            # convert the pixel value to height 
            # reference : https://docs.mapbox.com/data/tilesets/reference/mapbox-terrain-dem-v1/
            height = ((r * 256 * 256 + g * 256 + b) * 0.1) - 10000

            return height

        else :
            # raise an error and kill the program

            print("Tile not found")
            return None
        
    def get_heightmap(self,sw_lat:float,sw_lon:float,size_x:int,size_y:int) -> list:
        """
        Generate a list of latitude and longitude coordinates for a grid based on a 
        southwest corner point and specified dimensions.
        Retrieve elevation data for a list of latitude and longitude coordinates 
        from a Digital Elevation Model (DEM).
        Args:
            sw_lat (float): The latitude of the southwest corner of the grid.
            sw_lon (float): The longitude of the southwest corner of the grid.
            size_x (int): The width of the grid in meters.
            size_y (int): The height of the grid in meters.
        Returns:
            list: A list of elevation values.
        """
        equispace_x = size_x/globalParam.HEIGHTMAP_RESOLUTION
        equispace_y = size_y/globalParam.HEIGHTMAP_RESOLUTION
        start_point = Point(sw_lat,sw_lon)
        height_array = []
        for y in range(0,globalParam.HEIGHTMAP_RESOLUTION):
            current_latitude = distance(meters=equispace_y*y).destination(point=start_point, bearing=0)
            for x in range(0,globalParam.HEIGHTMAP_RESOLUTION):
                new_point = distance(meters=equispace_x*x).destination(point=current_latitude, bearing=90)
                '''
                Write a piece of code to get read the height from dem
                
                '''                
                # get the logic to get the height from dem

            
                height_array.append(self.get_amsl(new_point.latitude, new_point.longitude))
        
        
        return height_array


    def gen_terrain(self)-> list: 
        """
        Generate the terrain height map from the data received from Bing.

        Args:
            metadata_path (str): Path to metadata.

        Returns:
            list: Size and pose information.
        """

        #get the true boundaries as there is a padding non uniform padding added 
        bound_array = self.boundaries.split(',')
        boundaries = maptile_utiles.get_true_boundaries(bound_array,self.zoomlevel)
        sw = boundaries["southwest"]
        se = boundaries["southeast"]
        ne = boundaries["northeast"]

        #Caalculate the sizex, and sizey
        sizex = int(geodesic(sw, se).m)
        sizey = int(geodesic(se, ne).m)

        print("size of the terrian map",sizex,sizey)
        print("Using offline DEM data for heightmap generation")
        heightmap_array = self.get_heightmap(sw[0],sw[1],sizex,sizey)

        self.generate_height_image(heightmap_array,globalParam.HEIGHTMAP_RESOLUTION)
        origin_height = self.get_origin_height()
        print(origin_height)
        # Calculate posez, sizez
        posez = int(-1*(origin_height - np.min(heightmap_array)+5))
        sizez = np.max(heightmap_array) - np.min(heightmap_array)

        return sizex,sizey,sizez,posez
        

    def get_true_origin(self)-> list:
        bound_array = self.boundaries.split(',')
        boundaries = maptile_utiles.get_true_boundaries(bound_array,self.zoomlevel)

        sw = boundaries["southwest"]
        se = boundaries["southeast"]
        ne = boundaries["northeast"]
        origin_lon,origin_lat = float((se[1]+sw[1])/2),float((sw[0]+ne[0])/2) 
        print("true origin:",origin_lat," ",origin_lon)
        return {
            "latitude": origin_lat,
            "longitude": origin_lon,
            "altitude": self.get_amsl(origin_lat, origin_lon)
        }



    def gen_world(self) -> None:
        """
        Generate the gazebo world file.

        Args:

        Returns:
            None
        """

        template = FileWriter.read_template(os.path.join(globalParam.TEMPLATE_DIR_PATH ,'gazebo_world.txt'))
        origin_cord = self.get_true_origin()
        centre_height = self.get_amsl(origin_cord["latitude"],origin_cord["longitude"])
        FileWriter.write_world_file(template, self.model_name,origin_cord["latitude"],origin_cord["longitude"],os.path.join(globalParam.GAZEBO_WORLD_PATH, self.model_name),centre_height)


def generate_gazebo_world(tile_path):    

    # Main loop to select directory and trigger functions
    directory_path = tile_path
    print("Map tiles directory being used : ",directory_path)
    print("Generate gazebo world files are save to : ",os.path.join(globalParam.GAZEBO_WORLD_PATH,os.path.basename(directory_path)))
    if os.path.isfile(os.path.join(directory_path, 'metadata.json')) and directory_path != '':
        world_generator = heightmapgenerator(directory_path)
        world_generator.generate_ortho(directory_path)
        print("Satelliet image generated successfully")
        (sizex,sizey,sizez,posez) = world_generator.gen_terrain()
        print("Height map generated successfully")
        # Generate configuration file
        world_generator.gen_config()
        print("Gazebo world files generated successfully")
        print(sizex,sizey)
        # Generate SDF file for the world
        world_generator.gen_sdf(sizex,sizey,sizez, posez)
        world_generator.gen_world()
        shutil.rmtree(os.path.join(globalParam.TEMPORARY_SATELLITE_IMAGE, os.path.basename(directory_path)))
