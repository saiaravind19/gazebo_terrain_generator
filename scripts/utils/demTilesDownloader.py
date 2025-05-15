from urllib import request
import numpy as np
import cv2
import os
import time
from utils.gazebo_world_generator import maptile_utiles


def bit_to_img(url):
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


# Function to download and save the images (runs in a separate thread)
def download_dem_data(bound_array,output_directory):
    try:
        # some issue with boundary array

        print(bound_array)
        # Get the values from the input fields
        nw_lat_deg = float(bound_array["northwest"][0])
        nw_lon_deg = float(bound_array["northwest"][1])
        se_lat_deg = float(bound_array["southeast"][0])
        se_lon_deg = float(bound_array["southeast"][1])
        
        print(nw_lat_deg, nw_lon_deg, se_lat_deg, se_lon_deg)
        #Todo: check if directory exists
        MAX_LAT = 85.0511  # Web Mercator limit
        zoom_start = 10
        zoom_end = 11


        # Create base output directory
        os.makedirs(output_directory, exist_ok=True)

        for zoom in range(zoom_start, zoom_end + 1):

            nw_tilex, nw_tiley = maptile_utiles.lat_lon_to_tile(nw_lat_deg, nw_lon_deg, zoom)
            se_tilex, se_tiley = maptile_utiles.lat_lon_to_tile(se_lat_deg, se_lon_deg, zoom)

            start_tilex = min(nw_tilex, se_tilex)
            end_tilex =  max(nw_tilex, se_tilex)
            start_tiley = min(nw_tiley, se_tiley)
            end_tiley =  max(nw_tiley, se_tiley)

            print(f"Zoom Level: {zoom}")
            print(f"Tile Range X: {start_tilex} to {end_tilex}, Y: {start_tiley} to {end_tiley}")

            zoom_dir = os.path.join(output_directory, str(zoom))
            os.makedirs(zoom_dir, exist_ok=True)

            for x in range(start_tilex, end_tilex + 1):
                x_dir = os.path.join(zoom_dir, str(x))
                os.makedirs(x_dir, exist_ok=True)

                for y in range(start_tiley, end_tiley + 1):
                    tile_url = (
                        f"https://api.mapbox.com/raster/v1/mapbox.mapbox-terrain-dem-v1/"
                        f"{zoom}/{x}/{y}.webp?sku=101CUGorpzzyK&access_token=pk.eyJ1IjoicHJhdmlubWFsaTg1NCIsImEiOiJjbDM4Y2ZpaDIwMDdkM2JxbGM0ZWtkamxxIn0.VStYkAceQjhkW8StZekEvg"
                    )

                    try:
                        img = bit_to_img(tile_url)
                        file_path = os.path.join(x_dir, f"{y}.png")
                        cv2.imwrite(file_path, img)
                        print(f"Saved: {file_path}")
                        time.sleep(0.001)

                    except Exception as e:
                        print(f"Failed to download tile ({x}, {y}): {e}")

    except Exception as e:
        print(f"Download failed: {e}")