import cv2
import os
import numpy as np
import math
from PIL import Image
from multiprocessing import Pool, cpu_count

from utils.maptileUtils import maptile_utiles
from utils.utils import ConcatImage
from utils.param import globalParam


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
        

    @staticmethod
    def get_amsl(lat: float, lon: float):
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
        true_boundaries = maptile_utiles.get_true_boundaries(bound_array,zoomlevel)
        true_bound_array = [true_boundaries["southwest"][1], true_boundaries["southwest"][0],
                            true_boundaries["northeast"][1], true_boundaries["northeast"][0]]
        
        tile_number_boundaries = maptile_utiles.get_max_tilenumber(true_bound_array,globalParam.DEM_RESOLUTION)
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
            pool.map(ConcatImage._run_instance_method, args_list)

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

        tile_boundaries = maptile_utiles.get_true_boundaries(true_bound_array,globalParam.DEM_RESOLUTION)

        height,width = stitched_image.shape[:2]
        crop_px_cord = self.get_dem_px_bounds(true_boundaries,tile_boundaries,height,width)
        # Crop the image based on the true boundaries needed
        cropped_image = self.crop_dem_image(crop_px_cord,stitched_image) 
        height,width = cropped_image.shape[:2]
        cv2.imwrite(os.path.join(temp_output_dir, 'cropped_image.png'),cropped_image)

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
        self.heightmap.save(os.path.join(globalParam.GAZEBO_MODEL_PATH, model, 'textures', model+'_height_map.tif'), format="TIFF")

    def crop_dem_image(self,px_bound,height_map):
        cropped_image = height_map[px_bound["northwest"][1]:px_bound["southeast"][1], 
                                       px_bound["southwest"][0]:px_bound["northeast"][0]]
        return cropped_image
