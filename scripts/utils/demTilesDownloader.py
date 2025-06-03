from urllib import request
import numpy as np
import cv2
import os
import time
from utils.maptile_utils import maptile_utiles


def fetch_image_from_url(url):
    try:
        resp = request.urlopen(url)
        img = np.asarray(bytearray(resp.read()), dtype="uint8")
        img = cv2.imdecode(img, cv2.IMREAD_ANYCOLOR)
        if img is None:
            raise ValueError("Failed to decode image from URL.")
        return img
    except Exception as e:
        print(f"Failed to download or decode image from {url}: {e}")
        return None

def download_tile_image(zoom: int, x: int, y: int, output_dir: str) -> None:
    """Download and save a single tile image to the specified path."""
    tile_url = (
        f"https://api.mapbox.com/raster/v1/mapbox.mapbox-terrain-dem-v1/"
        f"{zoom}/{x}/{y}.webp?sku=101CUGorpzzyK&access_token=pk.eyJ1IjoicHJhdmlubWFsaTg1NCIsImEiOiJjbDM4Y2ZpaDIwMDdkM2JxbGM0ZWtkamxxIn0.VStYkAceQjhkW8StZekEvg"
    )
    img = fetch_image_from_url(tile_url)
    if img is not None:
        file_path = os.path.join(output_dir, f"{y}.png")
        cv2.imwrite(file_path, img)
        print(f"[INFO] Saved: {file_path}")
    else:
        print(f"[WARN] Skipped tile ({x}, {y}) due to download error.")


def download_dem_data(bound_array,output_directory, zoom_range: tuple = (10, 11)):
    """
    Download DEM data tiles within a bounding box.

    Args:
        boundary (dict): Contains 'northwest' and 'southeast' keys with (lat, lon) tuples.
        output_root (str): Root directory to save tiles.
        zoom_range (tuple): Range of zoom levels (start, end inclusive).
    """

    try:
        nw_lat, nw_lon = map(float, bound_array["northwest"])
        se_lat, se_lon = map(float, bound_array["southeast"])

        #Todo: check if directory exists
        MAX_LAT = 85.0511  # Web Mercator limit
        
        # Create base output directory
        maptile_utiles.dir_check(output_directory)

        for zoom in range(zoom_range[0], zoom_range[1] + 1):

            nw_tilex, nw_tiley = maptile_utiles.lat_lon_to_tile(nw_lat, nw_lon, zoom)
            se_tilex, se_tiley = maptile_utiles.lat_lon_to_tile(se_lat, se_lon, zoom)

            tilex_start, tilex_end = sorted((nw_tilex, se_tilex))
            tiley_start, tiley_end = sorted((nw_tiley, se_tiley))

            zoom_dir = os.path.join(output_directory, str(zoom))
            maptile_utiles.dir_check(zoom_dir)

            for x in range(tilex_start, tilex_end + 1):
                x_dir = os.path.join(zoom_dir, str(x))
                maptile_utiles.dir_check(x_dir)

                for y in range(tiley_start, tiley_end + 1):
                    download_tile_image(zoom, x, y, x_dir)
    except Exception as e:
        print(f"Download failed: {e}")