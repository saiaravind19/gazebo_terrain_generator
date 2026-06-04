#!/usr/bin/env python

from flask import Flask, request, jsonify, send_from_directory, send_file
import threading
import os
import uuid
import json
import shutil
from pathlib import Path
import mimetypes
from utils.dem_tiles_downloader import download_dem_data
from utils.building_downloader import download_streetmap_data
from utils.utils import Utils
from utils.gazebo_world_generator import GazeboTerrainGenerator
from utils.maptile_utils import MapTileUtils
from utils.height_map_generator import HeightmapGenerator
from utils.param import GlobalParam

app = Flask(__name__)
lock = threading.Lock()

task_status = {"status": "idle", "messages": []} # Global variable to track task status

def get_map_dir(map_name):
	return os.path.join(GlobalParam.OUTPUT_BASE_PATH, map_name)



def compute_auto_heightmap_size(bounds, dem_resolution):
	"""Return the nearest valid 2^n+1 heightmap size to the natural DEM tile dimensions."""
	dem_tiles = MapTileUtils.get_max_tilenumber(bounds, dem_resolution)
	x_count = dem_tiles['northeast'][0] - dem_tiles['northwest'][0] + 1
	y_count = dem_tiles['southwest'][1] - dem_tiles['northwest'][1] + 1
	natural_max = max(x_count * 512, y_count * 512)
	return HeightmapGenerator.get_nearest_map_size(natural_max)


def process_end_download(map_name, bounds, zoom_level, dem_resolution, include_buildings, polygon_vertices, api_key, heightmap_z_resolution, gazebo_version, target_heightmap_size, include_helipad=False, helipad_height=5.0):
	global task_status

	def progress(msg):
		task_status["messages"].append(msg)
		print(msg)

	try:
		task_status["status"] = "in_progress"
		map_dir = get_map_dir(map_name)

		# Write resolved target_heightmap_size to metadata for traceability
		metadata_path = os.path.join(map_dir, 'metadata.json')
		with open(metadata_path) as f:
			meta = json.load(f)
		meta['target_heightmap_size'] = target_heightmap_size
		with open(metadata_path, 'w') as f:
			json.dump(meta, f, indent=2)

		true_boundaries = MapTileUtils.get_true_boundaries(bounds, zoom_level)

		progress("Downloading elevation data (DEM)...")
		dem_path = os.path.join(map_dir, 'dem')
		download_dem_data(true_boundaries, dem_path, dem_resolution, api_key)

		if include_buildings:
			progress("Downloading building footprint data...")
			download_streetmap_data(true_boundaries, os.path.join(map_dir, 'building_tiles'), map_dir, api_key=api_key, polygon_vertices=polygon_vertices)

		terrain_generator = GazeboTerrainGenerator(map_dir, include_buildings, heightmap_z_resolution, gazebo_version, target_heightmap_size, include_helipad=include_helipad, helipad_height=helipad_height)
		terrain_generator.generate_gazebo_world(progress_cb=progress)

		for cleanup_dir in ('tiles', 'dem', 'building_tiles'):
			cleanup_path = os.path.join(map_dir, cleanup_dir)
			if os.path.isdir(cleanup_path):
				shutil.rmtree(cleanup_path)

		task_status["status"] = "completed"
		task_status["messages"].append("World generated successfully.")
		print("Gazebo world generation completed successfully.")

	except Exception as e:
		task_status["status"] = "failed"
		task_status["messages"].append(f"Error: {e}")
		print(f"Error during processing: {e}")



@app.route('/task-status', methods=['GET'])
def task_status_endpoint():
	global task_status
	messages = task_status["messages"]
	task_status["messages"] = []
	return jsonify({"code": 200, "message": {"status": task_status["status"], "messages": messages}})


@app.route('/download-tile', methods=['POST'])
def download_tile():
	postvars = request.form
	x = int(postvars['x'])
	y = int(postvars['y'])
	zoom = int(postvars['z'])
	map_name = str(postvars['mapName'])
	source = str(postvars['source'])
	api_key = str(postvars.get('mapboxApiKey', ''))

	file_path = os.path.join(get_map_dir(map_name), 'tiles', f"[{zoom},{y},{x}].png")

	if os.path.isfile(file_path):
		return jsonify({"code": 200, "message": "Tile already exists"})

	os.makedirs(os.path.dirname(file_path), exist_ok=True)
	code = Utils.download_file(source, file_path, x, y, zoom, api_key)

	if code == 200:
		return jsonify({"code": 200, "message": "Tile downloaded"})
	else:
		return jsonify({"code": code, "message": "Download failed"})


@app.route('/start-download', methods=['POST'])
def start_download():
	postvars = request.form
	map_name = postvars['mapName']
	zoom_level = int(postvars['maxZoom'])
	timestamp = int(postvars['timestamp'])
	polygon_vertices = json.loads(postvars['polygonVertices'])
	bounds = MapTileUtils.bounds_from_polygon(polygon_vertices)
	center = [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2]
	launch_location = list(map(float, postvars['launchLocation'].split(",")))
	include_buildings = postvars.get('includeBuildings', 'true').lower() == 'true'
	include_helipad = postvars.get('includeHelipad', 'false').lower() == 'true'
	helipad_height = float(postvars.get('helipadHeight', 5.0))
	gazebo_version = postvars.get('gazeboVersion', 'harmonic')
	target_heightmap_size_raw = postvars.get('targetHeightmapSize', 'auto')
	dem_resolution = min(zoom_level, GlobalParam.DEM_RESOLUTION)


	output_dir = get_map_dir(map_name)
	if os.path.exists(output_dir):
		shutil.rmtree(output_dir)
	os.makedirs(output_dir)

	metadata = {
		"name": map_name,
		"polygon_vertices": polygon_vertices,
		"bounds": ','.join(map(str, bounds)),
		"center": ','.join(map(str, center)),
		"zoom_level": zoom_level,
		"dem_resolution": dem_resolution,
		"launch_location": ','.join(map(str, launch_location)),
		"include_buildings": include_buildings,
		"include_helipad": include_helipad,
		"helipad_height": helipad_height,
		"gazebo_version": gazebo_version,
		"target_heightmap_size_setting": target_heightmap_size_raw,
		"timestamp": timestamp,
	}
	with open(os.path.join(output_dir, 'metadata.json'), 'w') as f:
		json.dump(metadata, f, indent=2)

	global task_status
	task_status = {"status": "idle", "messages": []}
	return jsonify({"code": 200, "message": "Metadata written"})


@app.route('/end-download', methods=['POST'])
def end_download():
	postvars = request.form
	map_name = postvars['mapName']
	zoom_level = int(postvars['maxZoom'])
	polygon_vertices = json.loads(postvars['polygonVertices'])
	bounds = MapTileUtils.bounds_from_polygon(polygon_vertices)
	include_buildings = postvars.get('includeBuildings', 'false').lower() == 'true'
	include_helipad = postvars.get('includeHelipad', 'false').lower() == 'true'
	helipad_height = float(postvars.get('helipadHeight', 5.0))
	gazebo_version = postvars.get('gazeboVersion')
	heightmap_z_resolution = 255 if gazebo_version == 'fortress' else 65535
	api_key = postvars.get('mapboxApiKey', '')
	dem_resolution = min(zoom_level, GlobalParam.DEM_RESOLUTION)

	target_heightmap_size_raw = postvars.get('targetHeightmapSize', 'auto')
	if target_heightmap_size_raw == 'auto':
		target_heightmap_size = compute_auto_heightmap_size(bounds, dem_resolution)
	else:
		target_heightmap_size = int(target_heightmap_size_raw)

	thread = threading.Thread(target=process_end_download, args=(map_name, bounds, zoom_level, dem_resolution, include_buildings, polygon_vertices, api_key, heightmap_z_resolution, gazebo_version, target_heightmap_size, include_helipad, helipad_height))
	thread.start()

	return jsonify({"code": 200, "message": "Download ended"})


@app.route('/valid-heightmap-sizes', methods=['GET'])
def valid_heightmap_sizes():
	return jsonify({"code": 200, "sizes": GlobalParam.VALID_HEIGHTMAP_SIZES})


@app.route('/estimate-texture-sizes', methods=['POST'])
def estimate_texture_sizes():
	postvars = request.form
	polygon_vertices = json.loads(postvars['polygonVertices'])
	zoom_level = int(postvars['zoomLevel'])
	tile_source = postvars.get('tileSource', '')
	dem_resolution = min(zoom_level, GlobalParam.DEM_RESOLUTION)
	bounds = MapTileUtils.bounds_from_polygon(polygon_vertices)

	# DEM tiles from Mapbox terrain-dem-v1 are 512×512px
	dem_tiles = MapTileUtils.get_max_tilenumber(bounds, dem_resolution)
	dem_x_count = dem_tiles['northeast'][0] - dem_tiles['northwest'][0] + 1
	dem_y_count = dem_tiles['southwest'][1] - dem_tiles['northwest'][1] + 1
	natural_hm_w = dem_x_count * 512
	natural_hm_h = dem_y_count * 512

	# Satellite tiles: 512px if @2x URL, 256px otherwise
	sat_tile_px = 512 if '@2x' in tile_source else 256
	sat_tiles = MapTileUtils.get_max_tilenumber(bounds, zoom_level)
	sat_x_count = sat_tiles['northeast'][0] - sat_tiles['northwest'][0] + 1
	sat_y_count = sat_tiles['southwest'][1] - sat_tiles['northwest'][1] + 1
	natural_tex_padded = max(sat_x_count * sat_tile_px, sat_y_count * sat_tile_px)

	auto_size = HeightmapGenerator.get_nearest_map_size(max(natural_hm_w, natural_hm_h))

	return jsonify({
		"code": 200,
		"natural_heightmap_width": natural_hm_w,
		"natural_heightmap_height": natural_hm_h,
		"auto_heightmap_size": auto_size,
		"valid_heightmap_sizes": GlobalParam.VALID_HEIGHTMAP_SIZES,
		"natural_texture_padded": natural_tex_padded
	})


@app.route('/download-world', methods=['GET'])
def download_world():
	map_name = request.args.get('mapName', '')
	if not map_name:
		return jsonify({"code": 400, "message": "mapName required"}), 400

	map_dir = get_map_dir(map_name)
	world_file = os.path.join(map_dir, f"{map_name}.world")

	if not os.path.isfile(world_file):
		return jsonify({"code": 404, "message": "World file not found"}), 404

	include_intermediary = request.args.get('includeIntermediary', 'false').lower() == 'true'

	import zipfile
	import io
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
		for fname in os.listdir(map_dir):
			fpath = os.path.join(map_dir, fname)
			if os.path.isfile(fpath) and not fname.endswith('.zip'):
				zf.write(fpath, f"{map_name}/{fname}")
		if include_intermediary:
			tiles_path = os.path.join(map_dir, 'tiles')
			if os.path.isdir(tiles_path):
				for fname in os.listdir(tiles_path):
					zf.write(os.path.join(tiles_path, fname), f"{map_name}/tiles/{fname}")
	buf.seek(0)
	return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=f"{map_name}.zip")


@app.route('/', defaults={'path': 'index.html'})
@app.route('/<path:path>')
def serve_static(path):
	file_dir = os.path.join(str(Path(__file__).resolve().parent), 'frontend')
	mime_type, _ = mimetypes.guess_type(path)
	return send_from_directory(file_dir, path, mimetype=mime_type)

if __name__ == '__main__':
	print("Starting Flask server...")
	app.run(host='127.0.0.1', port=8080, threaded=True)