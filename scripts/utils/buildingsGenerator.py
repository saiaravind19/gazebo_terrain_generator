import geopandas as gpd
import trimesh
from shapely.geometry import (
    Polygon, MultiPolygon,
    Point, MultiPoint,
    LineString, MultiLineString,
    GeometryCollection
)
from shapely.validation import make_valid
from pyproj import CRS,Transformer
import re

class GeoJSONToDAE:
    # ---------------- CONFIG ----------------
    DEFAULT_HEIGHT = 10.0
    LEVEL_HEIGHT = 3.0
    POINT_SIZE = 1.0
    LINE_WIDTH = 0.5
    LINE_HEIGHT = 2.0

    def __init__(self, input_geojson: str, output_dae: str):
        self.input_geojson = input_geojson
        self.output_dae = output_dae
        self.center_lat = None
        self.center_lon = None
        self.centre_amsl = None
        self.heightmap = None
        self.bounds = None
        self.pose_z = 0.0
        self.meshes = []

    # ---------------- HEIGHT UTILS ----------------
    def clean_height(self, value):
        if value is None:
            return None
        clean = re.sub(r"[^0-9.]", "", str(value))
        try:
            return float(clean)
        except ValueError:
            return None

    def get_height(self, props: dict) -> float:
        for tag in ["height", "building:height", "ele", "min_height"]:
            val = self.clean_height(props.get(tag))
            if val and val > 0:
                return val

        levels = self.clean_height(props.get("building:levels"))
        if levels:
            return levels * self.LEVEL_HEIGHT

        return self.DEFAULT_HEIGHT

# ---------------- PROJECTION ----------------
    def prepare_geodata(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        if gdf.crs is None:
            gdf.set_crs("EPSG:4326", inplace=True)
        else:
            gdf = gdf.to_crs("EPSG:4326")

        # Use the center calculated from the boundary array
        print(f"Aligning projection to Map Center: {self.center_lat:.6f}, {self.center_lon:.6f}")

        # Local Tangent Plane Projection centered on the Map Tile Center
        local_crs = CRS.from_proj4(
            f"+proj=aeqd +lat_0={self.center_lat} +lon_0={self.center_lon} "
            "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
        )

        return gdf.to_crs(local_crs)

    # ---------------- GEOMETRY NORMALIZATION ----------------
    def flatten_geometry(self, geom):
        if geom is None or geom.is_empty:
            return []

        if isinstance(geom, (Polygon, Point, LineString)):
            return [geom]

        if isinstance(geom, (MultiPolygon, MultiPoint, MultiLineString)):
            out = []
            for g in geom.geoms:
                out.extend(self.flatten_geometry(g))
            return out

        if isinstance(geom, GeometryCollection):
            out = []
            for g in geom.geoms:
                out.extend(self.flatten_geometry(g))
            return out

        return []

    # ---------------- PIXEL MATH ----------------
    def get_pixel_elevation(self, lat, lon):
        """Converts Lat/Lon to World Z using the Heightmap Image."""
        # 1. Unpack Bounds
        # Bounds: [min_lat (S), min_lon (W), max_lat (N), max_lon (E)]
        sw, ne = self.bounds['southwest'], self.bounds['northeast']
        lat_min, lat_max = sw[0], ne[0]
        lon_min, lon_max = sw[1], ne[1]
        
        width, height = self.heightmap.size

        # 2. Map Lat/Lon to Pixel Coordinates (Linear interpolation)
        # Note: Image Y origin (0) is usually top (North), so we flip logic for Lat
        px = int((lon - lon_min) / (lon_max - lon_min) * width)
        py = int((lat_max - lat) / (lat_max - lat_min) * height)

        # Clamp to image bounds
        px = max(0, min(px, width - 1))
        py = max(0, min(py, height - 1))

        # 3. Read Pixel Value (0-255)
        pixel_val = self.heightmap.getpixel((px, py))
        
        # 4. Convert to Local Terrain Height (Meters)
        # Formula: (Pixel / 255) * Total_Terrain_Z_Height
        local_z = (pixel_val / 255.0) * self.size_z
        
        # 5. Apply Terrain World Offset
        # The terrain model itself is shifted by terrain_pose_z in the world
        return local_z + self.pose_z

    def handle_polygon(self, geom: Polygon, height: float):
        if geom.area < 0.1:
            return None

        if not geom.is_valid:
            geom = make_valid(geom)
            if geom.is_empty:
                return None

        try:
            return trimesh.creation.extrude_polygon(geom, height)
        except Exception as e:
            print("Polygon extrusion failed:", e)
            return None

    def handle_point(self, geom: Point):
        mesh = trimesh.creation.box(
            extents=[self.POINT_SIZE] * 3
        )
        mesh.apply_translation([geom.x, geom.y, self.POINT_SIZE / 2])
        return mesh

    def handle_line(self, geom: LineString):
        if geom.length < 0.1:
            return None

        poly = geom.buffer(self.LINE_WIDTH / 2)

        if not poly.is_valid:
            poly = make_valid(poly)
            if poly.is_empty:
                return None

        try:
            return trimesh.creation.extrude_polygon(poly, self.LINE_HEIGHT)
        except Exception as e:
            print("Line extrusion failed:", e)
            return None

    # ---------------- PIPELINE ----------------
    def load(self) -> gpd.GeoDataFrame:
        print(f"Loading GeoJSON: {self.input_geojson}")
        gdf = gpd.read_file(self.input_geojson)
        return self.prepare_geodata(gdf)

    def process(self, gdf: gpd.GeoDataFrame):
        print(f"Processing {len(gdf)} features...")
        to_wgs84 = Transformer.from_crs(
            gdf.crs,            # local AEQD
            "EPSG:4326",
            always_xy=True
        )
        for _, row in gdf.iterrows():
            geom = row.geometry
            props = row.drop("geometry").to_dict()
            height = self.get_height(props)

            for g in self.flatten_geometry(geom):
                #The centroid is not always at the centre of the gemotry. So, assuming centroid and the rest of the building base is at the same heigth.
                centroid = g.centroid
                lon, lat = to_wgs84.transform(centroid.x, centroid.y)
                pose_z =  self.get_pixel_elevation(lat, lon)
                if isinstance(g, Polygon):
                    mesh = self.handle_polygon(g, height)
                elif isinstance(g, Point):
                    mesh = self.handle_point(g)
                elif isinstance(g, LineString):
                    mesh = self.handle_line(g)
                else:
                    mesh = None

                if mesh:
                    mesh.apply_translation([0, 0, pose_z])
                    self.meshes.append(mesh)

    def export(self):
        if not self.meshes:
            print("No geometry produced.")
            return

        print(f"Merging {len(self.meshes)} meshes...")
        combined = trimesh.util.concatenate(self.meshes)

        #center = combined.centroid
        #combined.apply_translation([-center[0], -center[1], -center[2]])

        combined.fix_normals()
        combined.export(self.output_dae)

        print(f"✔ Exported: {self.output_dae}")

    # ---------------- ONE-SHOT ----------------
    def run(self,origin_cords,size_z,pose_z,heightmap,boundaries):
        # Bounds are typically [South (min_lat), West (min_lon), North (max_lat), East (max_lon)]
        self.center_lat = origin_cords["latitude"]
        self.center_lon = origin_cords["longitude"]
        self.create_amsl = origin_cords["altitude"]
        self.size_z = size_z
        self.pose_z = pose_z
        self.heightmap = heightmap
        self.bounds = boundaries
        gdf = self.load()
        print("GeoData loaded.")

        self.process(gdf)
        self.export()
