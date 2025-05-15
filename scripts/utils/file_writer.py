import os
import json
import shutil




class FileWriter:

	slicer = None
	
	def ensureDirectory(lock, directory):
		'''
        Ensure the directory exists and create it if not.

        Args:
            lock (multiprocessing.Lock): A lock for thread-safe directory creation.
            directory (str): The directory path to ensure.

        Returns:
            str: The ensured directory path.		
		'''
		lock.acquire()
		try:

			if not os.path.exists('temp'):
				os.makedirs('temp')

			if not os.path.exists('output'):
				os.makedirs('output')

			os.makedirs(directory, exist_ok=True)

		finally:
			lock.release()

		return directory

	@staticmethod
	def addMetadata(lock, path, file, name, description, format, bounds, center,area, zoom_level, profile="mercator", tileSize=256):
		'''
        Add metadata to the specified path as a JSON file.

        Args:
            lock (multiprocessing.Lock): A lock for thread-safe operations.
            path (str): The directory path to ensure.
            file (str): The file name to store metadata.
            name (str): The name metadata.
            description (str): The description metadata.
            format (str): The format metadata.
            bounds (list): The bounds metadata as a list of float values.
            center (list): The center metadata as a list of float values.
            area (str): The area metadata.
            zoom_level (int): The zoom_level metadata.
            profile (str, optional): The profile metadata. Defaults to "mercator".
            tileSize (int, optional): The tileSize metadata. Defaults to 256.

        Returns:
            None
		'''
		FileWriter.ensureDirectory(lock, path)

		data = [
			("name", name),
			("description", description),
			("format", format), 
			("bounds", ','.join(map(str, bounds))), 
			("center", ','.join(map(str, center))), 
			("zoom_level", zoom_level), 
			("profile", profile), 
			("tilesize", str(tileSize)), 
			("area",area),
			("scheme", "xyz"), 
			("generator", "EliteMapper by Visor Dynamics"),
			("type", "overlay"),
			("attribution", "EliteMapper by Visor Dynamics"),
		]
		
		with open(path + "/metadata.json", 'w+') as jsonFile:
			json.dump(dict(data), jsonFile)

		return

	@staticmethod
	def addTile(lock, filePath, sourcePath, x, y, z, outputScale):
		'''
       Copy a file from sourcePath to filePath.

        Args:
            lock (multiprocessing.Lock): A lock for thread-safe operations.
            filePath (str): The path to save the copied file.
            sourcePath (str): The source file path to copy from.
            x (int): X-coordinate.
            y (int): Y-coordinate.
            z (int): Z-coordinate.
            outputScale (float): The output scale.

        Returns:
            None
		'''
		fileDirectory = os.path.dirname(filePath)
		FileWriter.ensureDirectory(lock, fileDirectory)
		
		shutil.copyfile(sourcePath, filePath)

		return

	@staticmethod
	def exists(filePath, x, y, z):
		'''
        Check if a file exists at the specified path.

        Args:
            filePath (str): The path to check for the file.
            x (int): X-coordinate.
            y (int): Y-coordinate.
            z (int): Z-coordinate.

        Returns:
            bool: True if the file exists, False otherwise.

		'''
		return os.path.isfile(filePath)


	@staticmethod
	def close(lock, path, file, zoom_level):
		'''
        Placeholder method for closing and recalculating metadata.

        Args:
            lock (multiprocessing.Lock): A lock for thread-safe operations.
            path (str): The directory path.
            file (str): The file name.
            zoom_level (int): The maximum zoom level.

        Returns:
            None

		'''
		#TODO recalculate bounds and center
		return
	
	@staticmethod
	def read_template(template_file_name):
		'''
        Read a template file and return its content as a string.

        Args:
            template_file_name (str): The path to the template file.

        Returns:
            str: The content of the template file.

		'''
		# Open template
		with open(template_file_name, "r") as template_file:
			# Read template
			template_hold_text = template_file.read()
			template = str(template_hold_text)
		return template
		
	
	@staticmethod
	def write_config_file(config_template, model_name,path,description="Gazebo 3d Terrian"):
		'''
        Write a configuration file with the provided template and model details.

        Args:
            config_template (str): The template content for the configuration file.
            model_name (str): The name of the model.
            path (str): The directory path to save the configuration file.
            description (str, optional): The description of the model. Defaults to "Gazebo 3d Terrian".

        Returns:
            None

		'''
		# Replace indicated values
		config_template = config_template.replace("$MODELNAME$", model_name)
		config_template = config_template.replace("$DESCRIPTION$", description)
    	# Ensure results are a string
		config_content = str(config_template)
    	# Open config file
		target = open(os.path.join(path,"model.config"), "w")
    	# Write to config file
		target.write(config_content)
    	# Close file
		target.close()
	
	@staticmethod
	def write_sdf_file(sdf_template,model_name,  size_x, size_y, size_z,origin_height,path):
		'''
        Write an SDF file with the provided template and model details.

        Args:
            sdf_template (str): The template content for the SDF file.
            model_name (str): The name of the model.
            size_x (float): The size in the x-direction.
            size_y (float): The size in the y-direction.
            size_z (float): The size in the z-direction.
            origin_height (float): The origin height.
            path (str): The directory path to save the SDF file.

        Returns:
            None

		'''
		
		heightmap = model_name+'_height_map.png'
		aerialimg = model_name+'_aerial.png'
    	# Filling in content
		sdf_template = sdf_template.replace("$MODELNAME$", model_name)
		sdf_template = sdf_template.replace("$SIZEX$", str(size_x))
		sdf_template = sdf_template.replace("$SIZEY$", str(size_y))
		sdf_template = sdf_template.replace("$SIZEZ$", str(size_z))
		sdf_template = sdf_template.replace("$POSZ$",str(origin_height))
		sdf_template = sdf_template.replace("$AERIALMAP$",str(aerialimg))
		sdf_template = sdf_template.replace("$HEIGHTMAP$",str(heightmap))

    	# Ensure results are a string
		sdf_content = str(sdf_template)
    	# Open file
		target = open(os.path.join(path,"model.sdf"), "w")

    	# Write to model.sdf
		target.write(sdf_content)
		target.close()

		
	@staticmethod
	def write_world_file(sdf_template,model_name,origin_lat,origin_long,path,origin_height):
		'''
		Write a world file with the provided template and model details.

        Args:
            sdf_template (str): The template content for the world file.
            model_name (str): The name of the model.
            origin_lat (float): The origin latitude.
            origin_long (float): The origin longitude.
            path (str): The directory path to save the world file.

        Returns:
            None

		'''
    	# Filling in content
		sdf_template = sdf_template.replace("$MODELNAME$", model_name)
		sdf_template = sdf_template.replace("$ORIGIN_LAT$", str(origin_lat))
		sdf_template = sdf_template.replace("$ORIGIN_LONG$", str(origin_long))
		sdf_template = sdf_template.replace("$ORIGIN_ELEVATION$", str(origin_height))

    	# Ensure results are a string
		sdf_content = str(sdf_template)
    	# Open file
		target = open(os.path.join(path,model_name+".world"), "w")

    	# Write to model.sdf
		target.write(sdf_content)
		target.close()