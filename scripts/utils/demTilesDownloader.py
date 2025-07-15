from urllib import request
import numpy as np
import cv2
import os
from utils.maptile_utils import maptile_utiles
from multiprocessing import Pool, cpu_count
from utils.param import globalParam

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

# Use the URL and api key defined in global param

def download_tile_image(args):
    zoom, x, y, output_dir = args
    tile_url = (
        f"https://api.mapbox.com/raster/v1/mapbox.mapbox-terrain-dem-v1/"
        f"{zoom}/{x}/{y}.webp?sku=101CUGorpzzyK&access_token={globalParam.MAPBOX_API_KEY}"
    )
    img = fetch_image_from_url(tile_url)
    if img is not None:
        file_path = os.path.join(output_dir, f"{y}.png")
        cv2.imwrite(file_path, img)
        print(f"[INFO] Saved: {file_path}")
    else:
        print(f"[WARN] Skipped tile ({x}, {y}) due to download error.")

def download_dem_data(bound_array, output_directory, zoom_range: tuple = (10, 11)):
    try:
        tasks = []
        nw_lat, nw_lon = map(float, bound_array["northwest"])
        se_lat, se_lon = map(float, bound_array["southeast"])
        maptile_utiles.dir_check(output_directory)

        for zoom in range(zoom_range[0], zoom_range[1] + 1):
            nw_tilex, nw_tiley = maptile_utiles.lat_lon_to_tile(nw_lat, nw_lon, zoom)
            se_tilex, se_tiley = maptile_utiles.lat_lon_to_tile(se_lat, se_lon, zoom)

            tilex_start, tilex_end = sorted((nw_tilex, se_tilex))
            tiley_start, tiley_end = sorted((nw_tiley, se_tiley))

            zoom_dir = os.path.join(output_directory, str(zoom))
            maptile_utiles.dir_check(zoom_dir)

            # Prepare all tile args
            for x in range(tilex_start, tilex_end + 1):
                x_dir = os.path.join(zoom_dir, str(x))
                maptile_utiles.dir_check(x_dir)
                for y in range(tiley_start, tiley_end + 1):
                    tasks.append((zoom, x, y, x_dir))

            # Use multiprocessing
        with Pool(processes=cpu_count()) as pool:  # You can tune the number here
            pool.map(download_tile_image, tasks)

    except Exception as e:
        print(f"Download failed: {e}")
