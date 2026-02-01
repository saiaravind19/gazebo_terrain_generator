#!/usr/bin/env python

from urllib.parse import urlparse
from urllib.parse import parse_qs
from urllib.parse import parse_qsl
import urllib.request
import uuid
import uuid
import ssl
import os
import cv2
import math
from utils.param import globalParam
from PIL import Image

class Utils:
	@staticmethod
	def randomString():
		return uuid.uuid4().hex.upper()[0:6]

	def getChildTiles(x, y, z):
		childX = x * 2
		childY = y * 2
		childZ = z + 1

		return [
			(childX, childY, childZ),
			(childX+1, childY, childZ),
			(childX+1, childY+1, childZ),
			(childX, childY+1, childZ),
		]

	def makeQuadKey(tile_x, tile_y, level):
		quadkey = ""
		for i in range(level):
			bit = level - i
			digit = ord('0')
			mask = 1 << (bit - 1)  # if (bit - 1) > 0 else 1 >> (bit - 1)
			if (tile_x & mask) != 0:
				digit += 1
			if (tile_y & mask) != 0:
				digit += 2
			quadkey += chr(digit)
		return quadkey

	@staticmethod
	def num2deg(xtile, ytile, zoom):
		n = 2.0 ** zoom
		lon_deg = xtile / n * 360.0 - 180.0
		lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
		lat_deg = math.degrees(lat_rad)
		return (lat_deg, lon_deg)

	@staticmethod
	def qualifyURL(url, x, y, z):

		scale22 = 23 - (z * 2)

		replaceMap = {
			"x": str(x),
			"y": str(y),
			"z": str(z),
			"scale:22": str(scale22),
			"quad": Utils.makeQuadKey(x, y, z),
		}

		for key, value in replaceMap.items():
			newKey = str("{" + str(key) + "}")
			url = url.replace(newKey, value)

		return url

	@staticmethod
	def mergeQuadTile(quadTiles):

		width = 0
		height = 0

		for tile in quadTiles:
			if(tile is not None):
				width = quadTiles[0].size[0] * 2
				height = quadTiles[1].size[1] * 2
				break

		if width == 0 or height == 0:
			return None

		canvas = Image.new('RGB', (width, height))

		if quadTiles[0] is not None:
			canvas.paste(quadTiles[0], box=(0,0))

		if quadTiles[1] is not None:
			canvas.paste(quadTiles[1], box=(width - quadTiles[1].size[0], 0))

		if quadTiles[2] is not None:
			canvas.paste(quadTiles[2], box=(width - quadTiles[2].size[0], height - quadTiles[2].size[1]))

		if quadTiles[3] is not None:
			canvas.paste(quadTiles[3], box=(0, height - quadTiles[3].size[1]))

		return canvas

	@staticmethod
	def downloadFile(url, destination, x, y, z):

		url = Utils.qualifyURL(url, x, y, z)

		code = 0

		# monkey patching SSL certificate issue
		# DONT use it in a prod/sensitive environment
		ssl._create_default_https_context = ssl._create_unverified_context

		try:
			path, response = urllib.request.urlretrieve(url, destination)
			code = 200
		except urllib.error.URLError as e:
			if not hasattr(e, "code"):
				print(e)
				code = -1
			else:
				code = e.code

		return code


	@staticmethod
	def downloadFileScaled(url, destination, x, y, z, outputScale):
		


		if outputScale == 1:
			return Utils.downloadFile(url, destination, x, y, z)

		elif outputScale == 2:

			childTiles = Utils.getChildTiles(x, y, z)
			childImages = []

			for childX, childY, childZ in childTiles:
				
				tempFile = Utils.randomString() + ".jpg"
				tempFilePath = os.path.join(globalParam.TEMPFILE_PATH, tempFile)

				code = Utils.downloadFile(url, tempFilePath, childX, childY, childZ)

				if code == 200:
					image = Image.open(tempFilePath)
				else:
					return code

				childImages.append(image)
			
			canvas = Utils.mergeQuadTile(childImages)
			# canvas.save(destination, "PNG")
			canvas.save(destination, "JPEG")
			
			return 200

		#TODO implement custom scale

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
		



