#!/usr/bin/env python

from flask import Flask, request, jsonify, send_from_directory
import threading
import os
import uuid
import base64
from pathlib import Path
import mimetypes
from utils.demTilesDownloader import download_dem_data
from utils.file_writer import FileWriter
from utils.utils import Utils
from utils.gazebo_world_generator import generate_gazebo_world
from utils.maptile_utils import maptile_utiles
from utils.param import globalParam

app = Flask(__name__)
lock = threading.Lock()


task_status = {"status": "idle"}  # Global variable to track task status


outputdirectory = None

def random_string():

	return uuid.uuid4().hex.upper()[0:6]




def process_end_download(bounds, zoom_level, outputDirectory, outputFile, filePath):
    global task_status
    try:
        task_status["status"] = "in_progress"

        # Perform the long-running task
        FileWriter.close(lock, os.path.join(globalParam.OUTPUT_BASE_PATH, outputDirectory), filePath, zoom_level)
        true_boundaries = maptile_utiles.get_true_boundaries(bounds, zoom_level)
        download_dem_data(true_boundaries, os.path.join(globalParam.OUTPUT_BASE_PATH, "dem"))
        orthodir_path = os.path.join(globalParam.OUTPUT_BASE_PATH, outputDirectory)
        generate_gazebo_world(orthodir_path)

        task_status["status"] = "completed"
        print("Gazebo world generation completed successfully.")
    except Exception as e:
        task_status["status"] = "failed"
        print(f"Error during processing: {e}")

@app.route('/task-status', methods=['GET'])
def task_status_endpoint():
	global task_status
	result = {}
	result["code"] = 200
	result["message"] = task_status
	return jsonify(result)

@app.route('/download-tile', methods=['POST'])
def download_tile():
	postvars = request.form
	x = int(postvars['x'])
	y = int(postvars['y'])
	z = int(postvars['z'])
	quad = str(postvars['quad'])
	timestamp = int(postvars['timestamp'])
	outputDirectory = str(postvars['outputDirectory'])
	outputFile = str(postvars['outputFile'])
	outputType = str(postvars['outputType'])
	outputScale = int(postvars['outputScale'])
	source = str(postvars['source'])

	replaceMap = {
		"x": str(x),
		"y": str(y),
		"z": str(z),
		"quad": quad,
		"timestamp": str(timestamp),
	}
	for key, value in replaceMap.items():
		outputDirectory = outputDirectory.replace(f"{{{key}}}", value)
		outputFile = outputFile.replace(f"{{{key}}}", value)
	print(outputDirectory)

	filePath = os.path.join(globalParam.OUTPUT_BASE_PATH, outputDirectory, outputFile)

	result = {}
	if FileWriter.exists(filePath, x, y, z):
		result["code"] = 200
		result["message"] = 'Tile already exists'
	else:
		tempFile = random_string() + ".jpg"
		tempFilePath = os.path.join(globalParam.TEMP_PATH, tempFile)
		result["code"] = Utils.downloadFileScaled(source, tempFilePath, x, y, z, outputScale)

		if os.path.isfile(tempFilePath):
			FileWriter.addTile(lock, filePath, tempFilePath, x, y, z, outputScale)
			with open(tempFilePath, "rb") as image_file:
				result["image"] = base64.b64encode(image_file.read()).decode("utf-8")
			os.remove(tempFilePath)
			result["message"] = 'Tile Downloaded'
		else:
			result["message"] = 'Download failed'

	return jsonify(result)

@app.route('/start-download', methods=['POST'])
def start_download():

	postvars = request.form
	outputType = postvars['outputType']
	outputScale = int(postvars['outputScale'])
	outputDirectory = postvars['outputDirectory']
	outputFile = postvars['outputFile']
	zoom_level = int(postvars['maxZoom'])
	timestamp = int(postvars['timestamp'])
	bounds = list(map(float, postvars['bounds'].split(",")))
	center = list(map(float, postvars['center'].split(",")))
	area_rect = postvars['area']

	outputDirectory = outputDirectory.replace("{timestamp}", str(timestamp))
	outputFile = outputFile.replace("{timestamp}", str(timestamp))
	filePath = os.path.join(globalParam.OUTPUT_BASE_PATH, outputDirectory, outputFile)

	FileWriter.addMetadata(
		lock, os.path.join(globalParam.OUTPUT_BASE_PATH, outputDirectory), filePath, outputFile,
		"Map Tiles Downloader via AliFlux", "jpg", bounds, center, area_rect,
		zoom_level, "mercator", 256 * outputScale
	)
	global task_status
	task_status = {"status": "idle"} 
	return jsonify({"code": 200, "message": "Metadata written"})

@app.route('/end-download', methods=['POST'])
def end_download():
	postvars = request.form
	outputType = postvars['outputType']
	outputScale = int(postvars['outputScale'])
	outputDirectory = postvars['outputDirectory']
	outputFile = postvars['outputFile']
	zoom_level = int(postvars['maxZoom'])
	timestamp = int(postvars['timestamp'])
	bounds = list(map(float, postvars['bounds'].split(",")))
	center = list(map(float, postvars['center'].split(",")))

	outputDirectory = outputDirectory.replace("{timestamp}", str(timestamp))
	outputFile = outputFile.replace("{timestamp}", str(timestamp))
	filePath = os.path.join(globalParam.OUTPUT_BASE_PATH, outputDirectory, outputFile)

	FileWriter.close(lock, os.path.join(globalParam.OUTPUT_BASE_PATH, outputDirectory), filePath, zoom_level)
    # Start the long-running task in a background thread
	thread = threading.Thread(target=process_end_download, args=(bounds, zoom_level, outputDirectory, outputFile, filePath))
	thread.start()

	return jsonify({"code": 200, "message": "Download ended"})

@app.route('/', defaults={'path': 'index.htm'})
@app.route('/<path:path>')
def serve_static(path):
	file_dir = os.path.join(str(Path(__file__).resolve().parent), 'UI')
	mime_type, _ = mimetypes.guess_type(path)
	return send_from_directory(file_dir, path, mimetype=mime_type)

if __name__ == '__main__':
	print("Starting Flask server...")
	app.run(host='0.0.0.0', port=8080, threaded=True)
