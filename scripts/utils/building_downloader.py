import os
import json
import requests
from typing import Dict, Any, List
from shapely.geometry import shape, Polygon as ShapelyPolygon
from utils.param import GlobalParam


# Public Overpass API endpoints (free, no API key). Buildings and their height
# metadata come straight from OpenStreetMap, the same source Mapbox derived its
# building tileset from. Several mirrors are listed because the public instances
# are frequently overloaded (HTTP 429/504); they are tried in order.
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# OSM/Overpass require a descriptive User-Agent; the default python-requests UA
# gets rejected with HTTP 406.
OVERPASS_HEADERS = {
    "User-Agent": "gazebo_terrain_generator/1.0 (https://github.com/saiaravind19/gazebo_terrain_generator)"
}


class BuildingDownloader:
    """
    Downloads building footprints from OpenStreetMap via the Overpass API for a
    given geographic area. Returns GeoJSON polygons carrying the raw OSM tags
    (``height``, ``building:levels``, ``building``, …) which the downstream
    mesh generator uses to extrude the buildings.
    """

    @staticmethod
    def _build_query(south: float, west: float, north: float, east: float) -> str:
        """Build an Overpass QL query for all buildings within the bounding box."""
        bbox = f"{south},{west},{north},{east}"
        return (
            "[out:json][timeout:60];"
            "("
            f'way["building"]({bbox});'
            f'relation["building"]({bbox});'
            ");"
            "out geom;"
        )

    @staticmethod
    def _ring_from_geometry(geometry: List[Dict[str, float]]) -> List[List[float]]:
        """Convert an Overpass geometry node list into a closed [lon, lat] ring."""
        ring = [[node["lon"], node["lat"]] for node in geometry
                if node.get("lat") is not None and node.get("lon") is not None]
        if len(ring) < 3:
            return []
        # Ensure the ring is closed (first == last)
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        return ring

    @classmethod
    def _element_to_features(cls, element: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert a single Overpass element (way or relation) into GeoJSON features."""
        props = element.get("tags", {})
        props = dict(props)  # copy so we can annotate
        props.setdefault("osm_id", element.get("id"))

        features = []
        el_type = element.get("type")

        if el_type == "way":
            ring = cls._ring_from_geometry(element.get("geometry", []))
            if ring:
                features.append({
                    "type": "Feature",
                    "id": f"way/{element.get('id')}",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": props,
                })

        elif el_type == "relation":
            # Treat each outer member as its own polygon. Inner rings (holes) are
            # ignored — building extrusion doesn't need courtyard cut-outs, and
            # this keeps multipolygon handling simple and crash-free.
            for member in element.get("members", []):
                if member.get("role") != "outer":
                    continue
                ring = cls._ring_from_geometry(member.get("geometry", []))
                if ring:
                    features.append({
                        "type": "Feature",
                        "id": f"relation/{element.get('id')}/{member.get('ref')}",
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                        "properties": props,
                    })

        return features

    def download_buildings(
        self,
        bound_array: Dict[str, Any],
        output_directory: str = None,
        polygon_vertices: list = None  # [[lng, lat], ...] drawn polygon from frontend
    ) -> Dict[str, Any]:
        """
        Download and read all buildings within the given bounds from Overpass.

        Args:
            bound_array: {
                "southwest": (lat, lon), "southeast": (lat, lon),
                "northwest": (lat, lon), "northeast": (lat, lon)
            }
            output_directory: Directory used to cache the raw Overpass response.
            polygon_vertices: The drawn polygon ([lng, lat] pairs). Buildings fully
                              inside it are kept.

        Returns:
            GeoJSON FeatureCollection with building polygons.
        """
        lats = [bound_array[c][0] for c in ("southwest", "southeast", "northwest", "northeast")]
        lons = [bound_array[c][1] for c in ("southwest", "southeast", "northwest", "northeast")]
        south, north = min(lats), max(lats)
        west, east = min(lons), max(lons)

        # ---- Fetch (with a small on-disk cache) ----
        data = None
        cache_path = None
        if output_directory:
            os.makedirs(output_directory, exist_ok=True)
            cache_path = os.path.join(output_directory, "overpass.json")
            if os.path.isfile(cache_path):
                try:
                    with open(cache_path) as f:
                        data = json.load(f)
                except Exception:
                    data = None

        if data is None:
            query = self._build_query(south, west, north, east)
            last_error = None
            for endpoint in OVERPASS_ENDPOINTS:
                try:
                    response = requests.post(endpoint, data={"data": query},
                                             headers=OVERPASS_HEADERS, timeout=90)
                    response.raise_for_status()
                    data = response.json()
                    break
                except Exception as e:
                    last_error = e
                    print(f"Overpass request to {endpoint} failed: {e}")
                    continue
            if data is None:
                print(f"All Overpass mirrors failed; skipping buildings. Last error: {last_error}")
                return {"type": "FeatureCollection", "features": []}
            if cache_path:
                with open(cache_path, "w") as f:
                    json.dump(data, f)

        # ---- Convert elements → GeoJSON features ----
        features_by_id = {}
        for element in data.get("elements", []):
            for feature in self._element_to_features(element):
                features_by_id[feature["id"]] = feature

        # ---- Filter to the drawn polygon (keep buildings fully inside it) ----
        if polygon_vertices:
            filter_shape = ShapelyPolygon(polygon_vertices)
            kept = {}
            for fid, feature in features_by_id.items():
                try:
                    if shape(feature["geometry"]).within(filter_shape):
                        kept[fid] = feature
                except Exception:
                    continue
            features_by_id = kept

        geojson = {
            "type": "FeatureCollection",
            "features": list(features_by_id.values()),
        }
        geojson = self._filter_extrudable_buildings(geojson)

        print(f"Downloaded {len(geojson['features'])} buildings from OpenStreetMap")
        return geojson

    def _filter_extrudable_buildings(self, geojson: Dict[str, Any]) -> Dict[str, Any]:
        """Keep only genuine buildings (drop building=no and any non-building junk)."""
        filtered_features = []
        for feature in geojson["features"]:
            props = feature.get("properties", {})
            building = str(props.get("building", "")).lower()
            if "building" in props and building != "no":
                filtered_features.append(feature)
        return {"type": "FeatureCollection", "features": filtered_features}

    def get_building_stats(self, geojson: Dict[str, Any]) -> Dict[str, Any]:
        """Get statistics about the downloaded buildings."""
        features = geojson.get("features", [])
        heights = []
        for feature in features:
            props = feature.get("properties", {})
            height = props.get("height") or props.get("render_height")
            if not height and props.get("building:levels"):
                try:
                    height = float(props["building:levels"]) * GeoJSONLevelHeight
                except (ValueError, TypeError):
                    height = None
            if height:
                try:
                    heights.append(float(str(height).split()[0]))
                except (ValueError, TypeError):
                    pass
        return {
            "total_buildings": len(features),
            "buildings_with_height": len(heights),
            "min_height": min(heights) if heights else 0,
            "max_height": max(heights) if heights else 0,
            "avg_height": sum(heights) / len(heights) if heights else 0,
        }


# Fallback level→height (m) used only for stats reporting; the mesh generator has
# its own authoritative value (GeoJSONToDAE.LEVEL_HEIGHT).
GeoJSONLevelHeight = 3.0


def download_streetmap_data(bound_array, output_directory, model_path, api_key: str = None,
                            zoom_level: int = GlobalParam.DEM_BUILDING_RESOLUTION,
                            polygon_vertices: list = None):
    """
    Download OSM building footprints for the given bounds and save them as
    ``buildings.geojson`` under ``model_path``.

    ``api_key`` and ``zoom_level`` are accepted for backward compatibility but are
    unused — Overpass needs no key and queries by bounding box, not by tile.
    """
    downloader = BuildingDownloader()

    street_map_path = os.path.join(model_path, 'buildings.geojson')
    buildings_geojson = downloader.download_buildings(
        bound_array=bound_array,
        output_directory=output_directory,
        polygon_vertices=polygon_vertices
    )

    stats = downloader.get_building_stats(buildings_geojson)
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
