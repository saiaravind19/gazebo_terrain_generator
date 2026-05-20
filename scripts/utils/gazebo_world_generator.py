import os
import cv2
import json
import numpy as np
from utils.file_writer import FileWriter, TEMPLATE_DIR
from utils.param import GlobalParam
from utils.maptile_utils import MapTileUtils
from utils.buildings_generator import GeoJSONToDAE
from utils.height_map_generator import HeightmapGenerator
from utils.utils import ConcatImage
from geopy.distance import geodesic
from geopy.point import Point


class OrthoGenerator(ConcatImage):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)


    def generate_ortho(self, tile_path: str, zoom_level: int) -> None:
        """
        Generate the aerial image of the map by stitching flat tile files.
        The selection may be a polygon, so some tiles in the bounding rectangle
        may be missing — those are filled with a gray placeholder.

        Args:
            tile_path (str): Path to the map directory (contains tiles/ and terrain_data/).
            zoom_level (int): Zoom level used when downloading tiles.

        Returns:
            None
        """
        tiles_dir = os.path.join(tile_path, 'tiles')
        output_dir = os.path.join(tile_path, 'terrain_data')
        os.makedirs(output_dir, exist_ok=True)

        # Get tile size from the first available tile to build the gray fill
        sample_fname = next((f for f in os.listdir(tiles_dir) if f.endswith('.png')), None)
        if sample_fname is None:
            raise ValueError(f"No tiles found in {tiles_dir} for zoom level {zoom_level}")
        sample_img = cv2.imread(os.path.join(tiles_dir, sample_fname))
        tile_h, tile_w = sample_img.shape[:2]
        gray_tile = np.full((tile_h, tile_w, 3), 128, dtype=np.uint8)

        stitched_image, tile_map, x_min, x_max, y_min, y_max = self.stitch_flat_tiles(
            tiles_dir, zoom_level, missing_fill=gray_tile
        )
        if tile_map is None or len(tile_map) == 0:
            raise ValueError(f"No tiles found in {tiles_dir} for zoom level {zoom_level}")

        if GlobalParam.DEBUG_TILE_BORDERS:
            n_cols = x_max - x_min + 1
            n_rows = y_max - y_min + 1
            border_color = (0, 0, 255)  # red in BGR
            # Vertical lines at each column boundary
            for col in range(n_cols + 1):
                px = col * tile_w
                cv2.line(stitched_image, (px, 0), (px, stitched_image.shape[0] - 1), border_color, 1)
            # Horizontal lines at each row boundary
            for row in range(n_rows + 1):
                py = row * tile_h
                cv2.line(stitched_image, (0, py), (stitched_image.shape[1] - 1, py), border_color, 1)
            # Label each tile with its [zoom,y,x] coordinates
            font = cv2.FONT_HERSHEY_SIMPLEX
            for col_idx, x in enumerate(range(x_min, x_max + 1)):
                for row_idx, y in enumerate(range(y_min, y_max + 1)):
                    label = f"[{zoom_level},{y},{x}]"
                    text_x = col_idx * tile_w + 4
                    text_y = row_idx * tile_h + 16
                    cv2.putText(stitched_image, label, (text_x, text_y), font, 0.4, (0, 0, 0), 2)
                    cv2.putText(stitched_image, label, (text_x, text_y), font, 0.4, border_color, 1)

        # Crop to polygon bounding box, removing tile-grid overhang on all sides
        bound_array = self.boundaries.split(',')
        lat_min = float(bound_array[1])
        lat_max = float(bound_array[3])
        lon_min = float(bound_array[0])
        lon_max = float(bound_array[2])
        tile_snap = MapTileUtils.get_true_boundaries(bound_array, zoom_level)
        snap_lat_max = tile_snap["northeast"][0]
        snap_lat_min = tile_snap["southwest"][0]
        snap_lon_max = tile_snap["northeast"][1]
        snap_lon_min = tile_snap["southwest"][1]
        h, w = stitched_image.shape[:2]
        px_w = int((lon_min - snap_lon_min) / (snap_lon_max - snap_lon_min) * w)
        px_e = int((lon_max - snap_lon_min) / (snap_lon_max - snap_lon_min) * w)
        py_n = int((snap_lat_max - lat_max) / (snap_lat_max - snap_lat_min) * h)
        py_s = int((snap_lat_max - lat_min) / (snap_lat_max - snap_lat_min) * h)
        stitched_image = stitched_image[py_n:py_s, px_w:px_e]

        # Paint areas outside the selected polygon gray
        h, w = stitched_image.shape[:2]
        poly_pts = [
            [int((lng - lon_min) / (lon_max - lon_min) * w),
             int((lat_max - lat) / (lat_max - lat_min) * h)]
            for lng, lat in self.polygon_vertices
        ]
        poly_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(poly_mask, [np.array(poly_pts, dtype=np.int32)], 255)
        stitched_image[poly_mask == 0] = 128

        # gz-sim normalizes texture UV by size_x for both axes, so a non-square image
        # causes the shorter dimension to be cut off. Pad to square with gray so all
        # tiles remain visible regardless of bounding box aspect ratio.
        if h != w:
            max_dim = max(h, w)
            padded = np.full((max_dim, max_dim, 3), 128, dtype=np.uint8)
            padded[:h, :w] = stitched_image
            stitched_image = padded

        # Save the stitched image. Level 3 balances speed and file size —
        # level 9 (max) is extremely slow on large images with little extra size reduction.
        compression_params = [cv2.IMWRITE_PNG_COMPRESSION, 3]
        cv2.imwrite(os.path.join(output_dir, 'aerial.png'), stitched_image, compression_params)



class GazeboTerrainGenerator(HeightmapGenerator, OrthoGenerator):
    def __init__(self, tile_path: str, include_buildings: bool, heightmap_z_resolution: int, gazebo_version: str, target_heightmap_size: int, **kwargs):
        super().__init__(**kwargs)
        self.tile_path = tile_path
        self.include_buildings = include_buildings
        self.heightmap_z_resolution = heightmap_z_resolution
        self.gazebo_version = gazebo_version
        self.target_heightmap_size = target_heightmap_size
        with open(os.path.join(self.tile_path, 'metadata.json')) as f:
            data = json.load(f)
            self.boundaries = data["bounds"]
            self.polygon_vertices = data["polygon_vertices"]
            self.launch_location = data["launch_location"]
            self.zoom_level = data["zoom_level"]
            self.dem_resolution = data["dem_resolution"]
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
        origin_lat = (float(bound_array[1]) + float(bound_array[3])) / 2
        origin_lon = (float(bound_array[0]) + float(bound_array[2])) / 2
        return {
            "latitude": origin_lat,
            "longitude": origin_lon,
            "altitude": HeightmapGenerator.get_amsl(origin_lat, origin_lon, os.path.join(self.tile_path, 'dem'), self.dem_resolution)
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
            "altitude": HeightmapGenerator.get_amsl(float(location_array[1]), float(location_array[0]), os.path.join(self.tile_path, 'dem'), self.dem_resolution)
            }

    def gen_world(self, size_x: float, size_y: float, size_z: float, pose_x: float, pose_y: float, pose_z: float) -> None:
        """
        Generate the Gazebo world file with the terrain model inlined.

        Args:
            size_x (float): Terrain size in x-direction (meters).
            size_y (float): Terrain size in y-direction (meters).
            size_z (float): Terrain size in z-direction (meters).
            pose_x (float): Model pose offset in x (meters).
            pose_y (float): Model pose offset in y (meters).
            pose_z (float): Model pose offset in z (meters).

        Returns:
            None
        """
        template_file = 'gazebo_fortress_world_template.sdf' if self.gazebo_version == 'fortress' else 'gazebo_world_template.sdf'
        template = FileWriter.read_template(os.path.join(TEMPLATE_DIR, template_file))
        launch_cord = self.get_launch_location()
        FileWriter.write_world_file(
            template,
            self.model_name,
            size_x, size_y, size_z,
            pose_x, pose_y, pose_z,
            launch_cord["latitude"],
            launch_cord["longitude"],
            launch_cord["altitude"],
            self.include_buildings,
            self.tile_path,
        )

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

        Args:
            None
        Returns:
            tuple: A tuple containing size_x, size_y, size_z, and pose_z.
        """
        bound_array = self.boundaries.split(',')
        lat_min = float(bound_array[1])
        lat_max = float(bound_array[3])
        lon_min = float(bound_array[0])
        lon_max = float(bound_array[2])
        sw = (lat_min, lon_min)
        se = (lat_min, lon_max)
        ne = (lat_max, lon_max)

        self.size_x = round(geodesic(sw, se).m, 2)
        self.size_y = round(geodesic(se, ne).m, 2)
        self.size_z = round(self.max_height - self.min_height,2)
        origin_coord = self.get_true_origin()
        launch_location = self.get_launch_location()
        pose_x,pose_y = self.get_offset(origin_coord,launch_location)
        launch_px, launch_py = self.get_launch_pixelcord(
            sw,
            ne,
            self.heightmap.size[0],
            self.heightmap.size[1],
            launch_location
        )

        # Calculate launch height and pose offset
        launch_height = self.heightmap.getpixel((launch_px, launch_py)) * self.size_z / self.heightmap_z_resolution
        pose_z = round(-launch_height, 2)

        return self.size_x,self.size_y,self.size_z,pose_x,pose_y,pose_z

    def generate_gazebo_world(self, progress_cb=None):
        """
            Generate the gazebo world along with world files.
        """
        def progress(msg):
            print(msg)
            if progress_cb:
                progress_cb(msg)

        if os.path.isfile(os.path.join(self.tile_path, 'metadata.json')) and self.tile_path != '':
            progress("Stitching satellite tiles...")
            self.generate_ortho(self.tile_path, self.zoom_level)

            progress("Processing heightmap...")
            self.generate_rgb_heightmap(self.tile_path, self.boundaries, self.zoom_level, os.path.join(self.tile_path, 'dem'), self.dem_resolution, self.target_heightmap_size)

            progress("Computing world dimensions...")
            (size_x, size_y, size_z, pose_x, pose_y, pose_z) = self.get_world_dimensions()

            if self.include_buildings:
                progress("Baking building models...")
                origin_coord = self.get_true_origin()
                terrain_data_dir = os.path.join(self.tile_path, 'terrain_data')
                street_map = os.path.join(terrain_data_dir, 'buildings.geojson')
                output_dae_file = os.path.join(terrain_data_dir, 'buildings.dae')
                bound_array = self.boundaries.split(',')
                lat_min = float(bound_array[1])
                lat_max = float(bound_array[3])
                lon_min = float(bound_array[0])
                lon_max = float(bound_array[2])
                polygon_bounds = {
                    "southwest": (lat_min, lon_min),
                    "southeast": (lat_min, lon_max),
                    "northwest": (lat_max, lon_min),
                    "northeast": (lat_max, lon_max),
                }
                geojson_to_dae = GeoJSONToDAE(street_map, output_dae_file)
                geojson_to_dae.run(origin_coord, size_z, pose_z, self.heightmap, self.heightmap_z_resolution, polygon_bounds)

            progress("Writing world file...")
            self.gen_world(size_x, size_y, size_z, pose_x, pose_y, pose_z)
