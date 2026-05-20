import cv2
import os
import numpy as np
import math
from PIL import Image
from utils.maptile_utils import MapTileUtils
from utils.utils import ConcatImage


# Valid Gazebo heightmap sizes (must be 2^n+1). Used for dropdown options and auto-sizing.
VALID_HEIGHTMAP_SIZES = [257, 513, 1025, 2049, 4097]

class HeightmapGenerator(ConcatImage):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.heightmap = None
        self.heightmap_z_resolution = 65535  # max pixel value; 65535 for 16-bit, 255 for 8-bit
        self.max_height = self.min_height = 0
        self.size_x=self.size_y=self.size_z=0


    def get_dem_px_bounds(self, true_boundaries, dem_snap_boundaries, height, width):
        crop_px_cord = {}
        lat_max = dem_snap_boundaries["northeast"][0]
        lat_min = dem_snap_boundaries["southwest"][0]
        lon_max = dem_snap_boundaries["northeast"][1]
        lon_min = dem_snap_boundaries["southwest"][1]

        for coord_name in true_boundaries.keys():
            lat, lon = true_boundaries[coord_name]
            # from boundaries and the desired lat/lon get the pixel coordinates
            px = int((lon - lon_min) / (lon_max - lon_min) * width)
            py = int((lat_max - lat) / (lat_max - lat_min) * height)
            crop_px_cord[coord_name] = (px, py)
        return crop_px_cord


    @staticmethod
    def get_amsl(lat: float, lon: float, dem_path: str, dem_resolution: int):
        """
        Get the height above mean sea level (AMSL) for a given latitude and longitude.
        Args:
            lat (float): Latitude in degrees.
            lon (float): Longitude in degrees.
            dem_path (str): Path to the DEM tile directory.
            dem_resolution (int): Zoom level used when downloading DEM tiles.
        Returns:
            float: Height above mean sea level in meters.
        """
        tile_x, tile_y = MapTileUtils.lat_lon_to_tile(lat, lon, dem_resolution)
        boundaries = MapTileUtils.get_tile_bounds(tile_x, tile_y, dem_resolution)
        lat_max = boundaries["northeast"][0]
        lat_min = boundaries["southwest"][0]
        lon_max = boundaries["northeast"][1]
        lon_min = boundaries["southwest"][1]
        dem_tile_path = os.path.join(dem_path, f"[{dem_resolution},{tile_y},{tile_x}].png")
        if os.path.isfile(dem_tile_path):
            # read the image — BGR format
            dem_img = cv2.imread(dem_tile_path)
            height, width = dem_img.shape[:2]
            px = int((lon - lon_min) / (lon_max - lon_min) * width)
            py = int((lat_max - lat) / (lat_max - lat_min) * height)
            b, g, r = dem_img[py, px]
            b, g, r = float(b), float(g), float(r)
            # convert pixel value to elevation in meters
            # reference: https://docs.mapbox.com/data/tilesets/reference/mapbox-terrain-dem-v1/
            height = ((r * 256 * 256 + g * 256 + b) * 0.1) - 10000
            return height
        else:
            print("Tile not found", tile_x, tile_y, dem_resolution, lat, lon)
            return None


    @staticmethod
    def get_nearest_map_size(dim):
        """
        Return the nearest valid Gazebo heightmap size (2^n + 1) to the given dimension.
        Valid sizes are defined in VALID_HEIGHTMAP_SIZES. Clamps to [257, 4097].
        """
        if dim <= 1:
            return VALID_HEIGHTMAP_SIZES[0]
        n = math.log2(max(dim - 1, 1))
        lower = (2 ** int(math.floor(n))) + 1
        upper = (2 ** int(math.ceil(n))) + 1
        lower = max(lower, VALID_HEIGHTMAP_SIZES[0])
        upper = min(upper, VALID_HEIGHTMAP_SIZES[-1])
        return lower if abs(dim - lower) <= abs(dim - upper) else upper


    def generate_rgb_heightmap(self, tile_path, boundaries, zoomlevel, dem_path: str, dem_resolution: int, target_heightmap_size: int) -> None:

        bound_array = boundaries.split(',')
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

        # Stitch all DEM tiles (no zoom filter — DEM dir contains only DEM tiles)
        stitched_image, _, _, _, _, _ = self.stitch_flat_tiles(dem_path, zoom_level=None)

        # dem_snap_boundaries: tile-aligned extent of the stitched DEM image at DEM zoom
        dem_snap_boundaries = MapTileUtils.get_true_boundaries(bound_array, dem_resolution)

        height, width = stitched_image.shape[:2]
        crop_px_cord = self.get_dem_px_bounds(polygon_bounds, dem_snap_boundaries, height, width)
        # Crop the image based on the true boundaries needed
        cropped_image = self.crop_dem_image(crop_px_cord, stitched_image)
        height, width = cropped_image.shape[:2]

        # Convert to float to avoid overflow during calculation
        cropped_image_float = cropped_image.astype(np.float32)
        # Calculate height map - changed to use float operations
        height_map = ((cropped_image_float[:, :, 2] * 256 * 256 + cropped_image_float[:, :, 1] * 256 + cropped_image_float[:, :, 0]) * 0.1) - 10000
        self.max_height = np.max(height_map)
        self.min_height = np.min(height_map)

        # Normalize to full pixel range. heightmap_z_resolution is 255 (8-bit) or 65535 (16-bit),
        # set by the caller based on the target simulator's PNG heightmap support.
        dtype = np.uint8 if self.heightmap_z_resolution == 255 else np.uint16
        height_img_normalized = ((height_map - np.min(height_map)) / (np.max(height_map) - np.min(height_map)) * self.heightmap_z_resolution).astype(dtype)

        size = target_heightmap_size
        # INTER_LINEAR avoids ringing artifacts that INTER_CUBIC introduces around
        # sharp SRTM quantization steps (~1m vertical steps on steep slopes)
        resized_map = cv2.resize(height_img_normalized, (size, size), interpolation=cv2.INTER_LINEAR)

        # Smooth out SRTM quantization steps. Source DEM is ~30m ground resolution so
        # smoothing by ~3 source pixels (scaled to heightmap size) removes quantization
        # stripes without losing real terrain shape.
        smooth_kernel = max(3, (size // 1000) * 2 + 1)  # ~31px for 4097, ~15px for 2049, always odd
        resized_map = cv2.GaussianBlur(resized_map, (smooth_kernel, smooth_kernel), sigmaX=0)

        terrain_data_dir = os.path.join(tile_path, 'terrain_data')
        os.makedirs(terrain_data_dir, exist_ok=True)

        # cv2 writes uint8 as 8-bit PNG and uint16 as 16-bit PNG automatically
        cv2.imwrite(os.path.join(terrain_data_dir, 'height_map.png'), resized_map)
        # Keep PIL image in memory for pixel lookups
        # 8-bit → mode 'L'; 16-bit → mode 'I' (PIL stores uint16 as int32 internally)
        if self.heightmap_z_resolution == 255:
            self.heightmap = Image.fromarray(resized_map, mode='L')
        else:
            self.heightmap = Image.fromarray(resized_map.astype(np.int32), mode='I')

        # Scale normal map strength proportionally to terrain range:
        # the heightmap is always normalized to 0-65535 regardless of real-world range,
        # so Sobel gradients are proportionally much stronger on flat terrain.
        # Dividing by a 100m reference keeps strength consistent across terrain types.
        terrain_range = self.max_height - self.min_height
        # Scale strength by 65535/heightmap_z_resolution so Sobel gradients are consistent
        # regardless of pixel range (8-bit values are 256× smaller than 16-bit ones)
        normal_map = HeightmapGenerator.generate_normal_map(resized_map, strength=0.0002 * (terrain_range / 100.0) * (65535 / self.heightmap_z_resolution))
        cv2.imwrite(os.path.join(terrain_data_dir, 'normal_map.png'), normal_map)

    @staticmethod
    def generate_normal_map(heightmap_u16: np.ndarray, strength: float) -> np.ndarray:
        """
        Derive a tangent-space normal map from a 16-bit heightmap using Sobel gradients.

        Normal encoding convention: RGB(128, 128, 255) = flat surface pointing straight up.
        Stored as BGR for OpenCV.

        Args:
            heightmap_u16: uint16 grayscale heightmap array (values 0-65535).
            strength: Gradient multiplier — scale by (terrain_range / 100.0) before passing
                      so the output is consistent across flat and hilly terrain.

        Returns:
            uint8 BGR normal map array, same spatial dimensions as input.
        """
        # Run Sobel on raw uint16 values — avoids near-zero gradients that result
        # from normalizing to [0,1] before differencing (pixel-to-pixel changes become tiny)
        h = heightmap_u16.astype(np.float32)

        # Blur before Sobel to suppress DEM quantization artifacts (SRTM ~1m steps appear
        # as horizontal/vertical stripes when Sobel runs at full strength on raw data)
        h = cv2.GaussianBlur(h, (9, 9), sigmaX=2.0)

        # Sobel gradients — rate of height change per pixel in X and Y
        dz_dx = cv2.Sobel(h, cv2.CV_32F, 1, 0, ksize=3)
        dz_dy = cv2.Sobel(h, cv2.CV_32F, 0, 1, ksize=3)

        # Normal = normalize(-dz/dx, -dz/dy, 1) — negated so normal tilts away from rising slope
        nx = -dz_dx * strength
        ny = -dz_dy * strength
        nz = np.ones_like(nx)

        length = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
        nx /= length
        ny /= length
        nz /= length

        # Map [-1, 1] → [0, 255]; store as BGR (B=Z, G=Y, R=X)
        normal_bgr = np.empty((*h.shape, 3), dtype=np.uint8)
        normal_bgr[:, :, 2] = np.clip((nx * 0.5 + 0.5) * 255, 0, 255).astype(np.uint8)  # R → X
        normal_bgr[:, :, 1] = np.clip((ny * 0.5 + 0.5) * 255, 0, 255).astype(np.uint8)  # G → Y
        normal_bgr[:, :, 0] = np.clip((nz * 0.5 + 0.5) * 255, 0, 255).astype(np.uint8)  # B → Z

        return normal_bgr

    def crop_dem_image(self, px_bound, height_map):
        cropped_image = height_map[px_bound["northwest"][1]:px_bound["southeast"][1],
                                   px_bound["southwest"][0]:px_bound["northeast"][0]]
        return cropped_image