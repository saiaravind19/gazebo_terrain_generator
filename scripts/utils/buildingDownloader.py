import os
import json
import requests
import mercantile
import mapbox_vector_tile
from pathlib import Path
from typing import List, Tuple, Dict, Any
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from .param import globalParam

class BuildingDownloader:
    """
    Downloads building data from Mapbox Vector Tiles for a given geographic area.
    Uses Mapbox's composite tileset which includes building footprints and heights from OpenStreetMap.
    """

    def __init__(self, api_key: str = None):
        """
        Initialize the building downloader.

        Args:
            api_key: Mapbox API key. If None, uses the global parameter.
        """
        self.api_key = api_key or globalParam.MAPBOX_API_KEY
        self.base_url = "https://api.mapbox.com/v4/mapbox.mapbox-streets-v8"

    def get_tiles_for_bounds(self, bounds: List[float], zoom: int = 15) -> List[Tuple[int, int, int]]:
        """
        Get list of tile coordinates that cover the given bounds.

        Args:
            bounds: [west_lon, south_lat, east_lon, north_lat]
            zoom: Zoom level (higher = more detail, 15-16 recommended for buildings)

        Returns:
            List of (x, y, z) tile coordinates
        """
        tiles = []
        for tile in mercantile.tiles(bounds[0], bounds[1], bounds[2], bounds[3], zoom):
            tiles.append((tile.x, tile.y, tile.z))
        return tiles

    def download_tile(self, x: int, y: int, z: int) -> Dict[str, Any]:
        """
        Download a single vector tile containing building data and convert to GeoJSON.

        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            z: Zoom level

        Returns:
            GeoJSON FeatureCollection with building polygons
        """
        url = f"{self.base_url}/{z}/{x}/{y}.vector.pbf?access_token={self.api_key}"

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Decode the Protocol Buffer vector tile
            tile_data = mapbox_vector_tile.decode(response.content)

            # Convert to GeoJSON
            return self._tile_to_geojson(tile_data, x, y, z)

        except requests.exceptions.RequestException as e:
            print(f"Error downloading tile {z}/{x}/{y}: {e}")
            return {"type": "FeatureCollection", "features": []}
        except Exception as e:
            print(f"Error decoding tile {z}/{x}/{y}: {e}")
            return {"type": "FeatureCollection", "features": []}

    def _tile_to_geojson(self, tile_data: Dict, x: int, y: int, z: int) -> Dict[str, Any]:
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

        # Check if building layer exists
        if 'building' not in tile_data:
            return {"type": "FeatureCollection", "features": []}

        building_layer = tile_data['building']
        extent = building_layer.get('extent', 4096)

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

    def download_buildings(self, bounds: List[float], zoom: int = 15,
                          output_path: str = None) -> Dict[str, Any]:
        """
        Download all buildings within the given bounds.

        Args:
            bounds: [west_lon, south_lat, east_lon, north_lat]
            zoom: Zoom level (15-16 recommended for building detail)
            output_path: Optional path to save the GeoJSON file

        Returns:
            GeoJSON FeatureCollection with all buildings
        """
        tiles = self.get_tiles_for_bounds(bounds, zoom)
        print(f"Downloading building data from {len(tiles)} tiles at zoom {zoom}...")

        # Use a dict to collect all features by ID so we can merge split buildings
        features_by_id = {}

        for i, (x, y, z) in enumerate(tiles):
            print(f"Downloading tile {i+1}/{len(tiles)}: {z}/{x}/{y}")
            data = self.download_tile(x, y, z)

            if data and "features" in data:
                # Collect buildings, merging those with the same ID across tiles
                for feature in data["features"]:
                    feature_id = self._get_feature_id(feature)

                    if feature_id not in features_by_id:
                        # First time seeing this building
                        features_by_id[feature_id] = feature
                    else:
                        # Building appears in multiple tiles - merge the geometries
                        features_by_id[feature_id] = self._merge_building_features(
                            features_by_id[feature_id],
                            feature
                        )

        # Create final GeoJSON from merged features
        geojson = {
            "type": "FeatureCollection",
            "features": list(features_by_id.values())
        }

        # Filter to only include buildings with extrude data
        geojson = self._filter_extrudable_buildings(geojson)

        print(f"Downloaded {len(geojson['features'])} unique buildings")

        # Save to file if path provided
        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(geojson, f, indent=2)
            print(f"Saved buildings to {output_path}")

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
