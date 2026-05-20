from urllib import request
import numpy as np
import cv2
import os
from utils.maptile_utils import MapTileUtils
from multiprocessing import Pool, cpu_count


def fetch_image_from_url(url: str):
    """
    Fetch an image from a URL and decode it into a NumPy array.
    Args:
        url (str): The URL of the image to fetch.
    Returns:
        np.ndarray: The decoded image as a NumPy array, or None if the download fails
    """
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


def check_dem_file(image_file: str) -> bool:
    """
    Check if the DEM tile image file exists.
    Args:
        image_file : str
    Returns:
        bool: True if the file exists, False otherwise.
    """
    return os.path.isfile(image_file)


def download_tile_image(args: tuple) -> None:
    """
    Download a single DEM tile image and save it to the specified directory.
    Args:
        args (tuple): A tuple containing zoom level, x tile number, y tile number,
                      output directory, and Mapbox API key.
    Returns:
        None
    """
    zoom, tile_x, tile_y, output_dir, api_key = args
    tile_url = (
        f"https://api.mapbox.com/raster/v1/mapbox.mapbox-terrain-dem-v1/"
        f"{zoom}/{tile_x}/{tile_y}.webp?sku=101CUGorpzzyK&access_token={api_key}"
    )
    img = fetch_image_from_url(tile_url)
    if img is not None:
        file_path = os.path.join(output_dir, f"[{zoom},{tile_y},{tile_x}].png")
        cv2.imwrite(file_path, img)
    else:
        print(f"[WARN] Skipped tile ({tile_x}, {tile_y}) due to download error.")


def download_dem_data(bound_array, output_directory, zoom: int, api_key: str) -> None:
    """
    Download DEM data for a specified bounding box at a given zoom level.
    Args:
        bound_array: Bounding box dict with 'northwest' and 'southeast' keys.
        output_directory (str): The directory where the downloaded DEM tiles will be saved.
        zoom (int): Zoom level for DEM tiles. Should be min(satellite_zoom, 13) —
                    Mapbox terrain-dem-v1 source data is ~30m (SRTM), so zoom > 13
                    yields no additional real-world elevation detail.
        api_key (str): Mapbox API key.
    Returns:
        None
    """
    try:
        tasks = []
        nw_lat, nw_lon = map(float, bound_array["northwest"])
        se_lat, se_lon = map(float, bound_array["southeast"])
        MapTileUtils.dir_check(output_directory)

        nw_tile_x, nw_tile_y = MapTileUtils.lat_lon_to_tile(nw_lat, nw_lon, zoom)
        se_tile_x, se_tile_y = MapTileUtils.lat_lon_to_tile(se_lat, se_lon, zoom)

        tile_x_start, tile_x_end = sorted((nw_tile_x, se_tile_x))
        tile_y_start, tile_y_end = sorted((nw_tile_y, se_tile_y))
        for tile_x in range(tile_x_start, tile_x_end + 1):
            for tile_y in range(tile_y_start, tile_y_end + 1):
                dem_file = os.path.join(output_directory, f"[{zoom},{tile_y},{tile_x}].png")
                if not check_dem_file(dem_file):
                    tasks.append((zoom, tile_x, tile_y, output_directory, api_key))

        with Pool(processes=cpu_count()) as pool:
            pool.map(download_tile_image, tasks)

    except Exception as e:
        print(f"Download failed: {e}")
