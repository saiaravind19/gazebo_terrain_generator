import os
import json
import requests
import mapbox_vector_tile
from pathlib import Path
from typing import List, Tuple, Dict, Any
from shapely.geometry import shape, mapping, Polygon as ShapelyPolygon
from shapely.ops import unary_union
from utils.maptile_utils import MapTileUtils
import mercantile
from multiprocessing import Pool, cpu_count

# Mapbox streets-v8 vector tiles have full building footprint detail at zoom 15;
# higher zoom levels add no additional buildings.
BUILDING_TILE_ZOOM = 15


class BuildingDownloader:
    """
    Downloads building data from Mapbox Vector Tiles for a given geographic area.
    Uses Mapbox's composite tileset which includes building footprints and heights from OpenStreetMap.
    """

    def __init__(self):
        """
        Initialize the building downloader.

        Args:
            api_key: Mapbox API key. If None, uses the global parameter.
        """

    @staticmethod
    def download_tile(zoom : int, tile_x: int, tile_y: int, output_dir: str, api_key: str) -> Dict[str, Any]:
        """
        Download a single vector tile containing building data and convert to GeoJSON.

        Args:
            zoom: Zoom level
            tile_x: Tile X coordinate
            tile_y: Tile Y coordinate
            api_key: Mapbox API key.

        Returns:
            GeoJSON FeatureCollection with building polygons
        """
        base_url = "https://api.mapbox.com/v4/mapbox.mapbox-streets-v8"

        url = f"{base_url}/{zoom}/{tile_x}/{tile_y}.vector.pbf?access_token={api_key}"

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Decode the Protocol Buffer vector tile and cache as JSON
            tile_data = mapbox_vector_tile.decode(response.content)
            with open(f"{output_dir}/{tile_y}.json", "w") as f:
                json.dump(tile_data, f)
        except Exception as e:
            print(f"Error while downloading tile {zoom}/{tile_x}/{tile_y}: {e}")
            return {"type": "FeatureCollection", "features": []}

    def _tile_to_geojson(self, tile_path: str, x: int, y: int, z: int) -> Dict[str, Any]:
        """
        Convert decoded vector tile data to GeoJSON.

        Args:
            tile_data: Decoded vector tile data
            x: Tile X coordinate
            y: Tile Y coordinate
            z: Zoom level

        Returns:
            GeoJSON FeatureCollection
        """
        features = []

        tile_data = json.load(open(tile_path, "r"))
        #print(f"Loaded tile data from {tile_path}")
        # Check if building layer exists
        if 'building' not in tile_data:
            return {"type": "FeatureCollection", "features": []}

        building_layer = tile_data['building']
        extent = building_layer.get('extent', 4096)

        ############### use map utils pkg for the same ##########
        # Get tile bounds for coordinate conversion
        bounds = mercantile.bounds(x, y, z)

        for feature in building_layer.get('features', []):
            # Convert tile coordinates to lat/lon
            geojson_feature = self._feature_to_geojson(
                feature, bounds, extent
            )
            if geojson_feature:
                features.append(geojson_feature)

        return {"type": "FeatureCollection", "features": features}

    def _feature_to_geojson(self, feature: Dict, bounds: mercantile.LngLatBbox,
                           extent: int) -> Dict[str, Any]:
        """
        Convert a vector tile feature to GeoJSON.

        Args:
            feature: Vector tile feature
            bounds: Tile bounds
            extent: Tile extent (usually 4096)

        Returns:
            GeoJSON feature
        """
        geometry = feature.get('geometry')
        properties = feature.get('properties', {})

        if not geometry:
            return None

        # Convert tile coordinates to geographic coordinates
        geom_type = geometry['type']
        coordinates = geometry['coordinates']

        def tile_to_lon(x):
            return bounds.west + (x / extent) * (bounds.east - bounds.west)

        def tile_to_lat(y):
            # mapbox-vector-tile library uses origin at bottom (y=0 at south)
            return bounds.south + (y / extent) * (bounds.north - bounds.south)

        def convert_coords(coords):
            if isinstance(coords[0], (int, float)):
                return [tile_to_lon(coords[0]), tile_to_lat(coords[1])]
            return [convert_coords(c) for c in coords]

        geojson_coords = convert_coords(coordinates)

        return {
            "type": "Feature",
            "id": feature.get('id'),
            "geometry": {
                "type": geom_type,
                "coordinates": geojson_coords
            },
            "properties": properties
        }

    def download_buildings(
        self,
        bound_array: Dict[str, Any],
        api_key: str = None,
        zoom: int = BUILDING_TILE_ZOOM,
        output_directory: str = None,
        polygon_vertices: list = None  # [[lng, lat], ...] drawn polygon from frontend
    ) -> Dict[str, Any]:
        """
        Download and read all buildings within the given bounds.

        Args:
            bound_array: {
                "northwest": [lat, lon],
                "southeast": [lat, lon]
            }
            zoom: Zoom level
            output_directory: Directory to store tiles and optional output

        Returns:
            GeoJSON FeatureCollection with merged buildings
        """

        features_by_id = {}

        # ---- Bounds → tile range (SOURCE OF TRUTH) ----
        nw_lat, nw_lon = map(float, bound_array["northwest"])
        se_lat, se_lon = map(float, bound_array["southeast"])

        nw_tile_x, nw_tile_y = MapTileUtils.lat_lon_to_tile(nw_lat, nw_lon, zoom)
        se_tile_x, se_tile_y = MapTileUtils.lat_lon_to_tile(se_lat, se_lon, zoom)

        tile_x_start, tile_x_end = sorted((nw_tile_x, se_tile_x))
        tile_y_start, tile_y_end = sorted((nw_tile_y, se_tile_y))

        # ---- Directory setup ----
        MapTileUtils.dir_check(output_directory)
        zoom_dir = os.path.join(output_directory, str(zoom))
        MapTileUtils.dir_check(zoom_dir)

        # ---- Prepare download tasks ----
        tasks = []
        for tile_x in range(tile_x_start, tile_x_end + 1):
            tile_x_dir = os.path.join(zoom_dir, str(tile_x))
            MapTileUtils.dir_check(tile_x_dir)
            for tile_y in range(tile_y_start, tile_y_end + 1):
                tile_path = os.path.join(tile_x_dir, f"{tile_y}.json")
                if not os.path.isfile(tile_path):
                    tasks.append((zoom, tile_x, tile_y, tile_x_dir, api_key))

        # ---- Download missing tiles ----
        if tasks:
            print(f"Downloading {len(tasks)} tiles…")
            with Pool(processes=cpu_count()) as pool:
                pool.starmap(BuildingDownloader.download_tile, tasks)

        filter_shape = ShapelyPolygon(polygon_vertices)

        # ---- READ tiles ONE BY ONE (important part) ----
        for tile_x in range(tile_x_start, tile_x_end + 1):
            for tile_y in range(tile_y_start, tile_y_end + 1):
                tile_path = os.path.join(zoom_dir, str(tile_x), f"{tile_y}.json")

                if not os.path.isfile(tile_path):
                    print(f"Warning: Missing tile file {tile_path}")
                    continue  # failed or missing tile

                # Convert tile → GeoJSON
                tile_geojson = self._tile_to_geojson(tile_path, tile_x, tile_y, zoom)
                #print(f"Processed tile {zoom}/{tile_x}/{tile_y} with {len(tile_geojson.get('features', []))} buildings")
                if not tile_geojson or "features" not in tile_geojson:
                    continue

                # ---- Merge buildings by ID ----
                for feature in tile_geojson["features"]:
                    geom = shape(feature["geometry"])

                    # ---- EARLY TRUE BOUNDARY FILTER ----
                    # Use within() not intersects() — exclude buildings that merely touch the edge
                    if not geom.within(filter_shape):
                        continue
                    feature_id = self._get_feature_id(feature)

                    if feature_id not in features_by_id:
                        features_by_id[feature_id] = feature
                    else:
                        features_by_id[feature_id] = self._merge_building_features(
                            features_by_id[feature_id],
                            feature
                        )

        # ---- Final GeoJSON ----
        geojson = {
            "type": "FeatureCollection",
            "features": list(features_by_id.values())
        }

        geojson = self._filter_extrudable_buildings(geojson)

        print(f"Downloaded & merged {len(geojson['features'])} unique buildings")

        return geojson

    def _get_feature_id(self, feature: Dict[str, Any]) -> str:
        """
        Generate a unique ID for a building feature based on its coordinates.

        Args:
            feature: GeoJSON feature

        Returns:
            Unique identifier string
        """
        if "id" in feature:
            return str(feature["id"])

        # Use first coordinate as ID
        coords = feature.get("geometry", {}).get("coordinates", [[]])
        if coords and len(coords) > 0 and len(coords[0]) > 0:
            first_coord = coords[0][0] if isinstance(coords[0][0], list) else coords[0]
            return f"{first_coord[0]:.6f},{first_coord[1]:.6f}"

        return str(hash(json.dumps(feature)))

    def _merge_building_features(self, feature1: Dict[str, Any], feature2: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge two building features that represent the same building split across tiles.

        Args:
            feature1: First GeoJSON feature
            feature2: Second GeoJSON feature (same building, different tile)

        Returns:
            Merged GeoJSON feature with combined geometry
        """
        try:
            # Convert GeoJSON to shapely geometries
            geom1 = shape(feature1["geometry"])
            geom2 = shape(feature2["geometry"])

            # Union the geometries to merge them
            merged_geom = unary_union([geom1, geom2])

            # Convert back to GeoJSON
            merged_feature = {
                "type": "Feature",
                "id": feature1.get("id"),
                "geometry": mapping(merged_geom),
                "properties": feature1.get("properties", {})
            }

            return merged_feature

        except Exception as e:
            print(f"Warning: Failed to merge building features: {e}")
            # If merge fails, return the first feature
            return feature1

    def _filter_extrudable_buildings(self, geojson: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter buildings to only include those with height/extrusion data.

        Args:
            geojson: Input GeoJSON FeatureCollection

        Returns:
            Filtered GeoJSON with only extrudable buildings
        """
        filtered_features = []

        for feature in geojson["features"]:
            props = feature.get("properties", {})

            # Check for height or building height properties
            has_height = (
                "height" in props or
                "min_height" in props or
                "render_height" in props or
                props.get("extrude") == "true" or
                props.get("type") == "building"
            )

            if has_height:
                filtered_features.append(feature)

        return {
            "type": "FeatureCollection",
            "features": filtered_features
        }

    def get_building_stats(self, geojson: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get statistics about the downloaded buildings.

        Args:
            geojson: GeoJSON FeatureCollection

        Returns:
            Dictionary with building statistics
        """
        features = geojson.get("features", [])
        heights = []

        for feature in features:
            props = feature.get("properties", {})
            height = props.get("height") or props.get("render_height", 0)
            if height:
                heights.append(float(height))

        stats = {
            "total_buildings": len(features),
            "buildings_with_height": len(heights),
            "min_height": min(heights) if heights else 0,
            "max_height": max(heights) if heights else 0,
            "avg_height": sum(heights) / len(heights) if heights else 0
        }

        return stats



def download_streetmap_data(bound_array, output_directory, model_path, api_key: str = None, zoom_level: int = BUILDING_TILE_ZOOM, polygon_vertices: list = None):
    #try:
    downloader = BuildingDownloader()

    # Download buildings at zoom 15 (good detail for buildings)
    street_map_path = os.path.join(model_path,
        'buildings.geojson'
    )
    buildings_geojson = downloader.download_buildings(
        bound_array=bound_array,
        api_key=api_key,
        zoom=zoom_level,
        output_directory=output_directory,
        polygon_vertices=polygon_vertices
    )
    # Print statistics
    stats = downloader.get_building_stats(buildings_geojson)
    # Save to file if path provided
    if not os.path.exists(model_path):
        os.makedirs(model_path)
    with open(street_map_path, 'w') as f:
        json.dump(buildings_geojson, f, indent=2)
    print(f"Saved buildings to {street_map_path}")
    print(f"Buildings downloaded: {stats['total_buildings']}")
    print(f"Buildings with height data: {stats['buildings_with_height']}")
    if stats['buildings_with_height'] > 0:
        print(f"Height range: {stats['min_height']:.1f}m - {stats['max_height']:.1f}m")
        print(f"Average height: {stats['avg_height']:.1f}m")

    #except Exception as e:
    #    print(f"Download failed: {e}")
