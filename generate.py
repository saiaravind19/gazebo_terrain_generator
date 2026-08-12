#!/usr/bin/env python3
import argparse
import gzip
import json
import os
import sys
from pathlib import Path

import mapbox_vector_tile
import mercantile
import planetary_computer
import requests
import rioxarray
from pystac_client import Client
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform
from shapely.validation import make_valid

from pipeline.bbox import BoundingBox, parse_bbox
from pipeline import gba as gba_mod
from pipeline import osm_raw as osm_raw_mod
from pipeline import osm2world as osm2world_mod
from pipeline import heightmap as heightmap_mod
from pipeline import world as world_mod
from pipeline import terrain_wrap as terrain_wrap_mod

REPO_ROOT = Path(__file__).resolve().parent
ASSETS_DIR = REPO_ROOT / "generated_assets"
DEM_DIR = ASSETS_DIR / "dem"
OSM_TILES_DIR = ASSETS_DIR / "osm" / "tiles"
OSM_FEATURES_DIR = ASSETS_DIR / "osm" / "features"
OVERPASS_DIR = ASSETS_DIR / "osm" / "overpass"
OSM_RAW_DIR = ASSETS_DIR / "osm" / "raw"
GBA_DIR = ASSETS_DIR / "gba"

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"

OVERPASS_TAGS = {
    "trees": [("natural", "tree")],
    "power_poles": [("power", "pole")],
    "power_towers": [("power", "tower")],
    "power_lines": [("power", "line"), ("power", "minor_line")],
    "streetlights": [("highway", "street_lamp")],
    "traffic_signals": [("highway", "traffic_signals")],
    "bus_stops": [("highway", "bus_stop")],
    "benches": [("amenity", "bench")],
    "post_boxes": [("amenity", "post_box")],
    "fire_hydrants": [("emergency", "fire_hydrant")],
    "manholes": [("man_made", "manhole")],
}

STAC_ENDPOINT = "https://planetarycomputer.microsoft.com/api/stac/v1"
DEM_COLLECTION = "cop-dem-glo-30"

OFM_TILEJSON_URL = "https://tiles.openfreemap.org/planet"
OSM_ZOOM = 14
OFM_USER_AGENT = "gazebo-world-generator/0.1"

LAYER_EXTRACT = {
    "buildings": {"layer": "building"},
    "roads": {
        "layer": "transportation",
        "exclude_class": {"path", "rail", "ferry", "aerialway"},
    },
    "sidewalks": {
        "layer": "transportation",
        "include_class": {"path"},
    },
    "landcover": {
        "layer": "landcover",
        "include_class": {"grass", "wood", "forest", "sand", "farmland", "ice", "wetland"},
    },
    "landuse": {
        "layer": "landuse",
        "include_class": {
            "park",
            "cemetery",
            "recreation_ground",
            "playground",
            "pitch",
            "school",
            "kindergarten",
            "hospital",
            "residential",
            "commercial",
            "retail",
            "industrial",
        },
    },
    "water": {"layer": "water"},
    "waterway": {"layer": "waterway"},
    "pois": {"layer": "poi"},
}


def bbox_key(bbox: BoundingBox) -> str:
    return bbox.key()


def dem_path_for(bbox: BoundingBox) -> Path:
    return DEM_DIR / f"cop_dem_glo30_{bbox_key(bbox)}.tif"


def download_dem(bbox: BoundingBox, force: bool = False) -> Path:
    DEM_DIR.mkdir(parents=True, exist_ok=True)
    out_path = dem_path_for(bbox)
    if out_path.exists() and not force:
        print(f"DEM cache hit: {out_path}")
        return out_path

    print(f"searching {DEM_COLLECTION} on Planetary Computer...")
    client = Client.open(STAC_ENDPOINT, modifier=planetary_computer.sign_inplace)
    search = client.search(
        collections=[DEM_COLLECTION],
        bbox=[bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat],
    )
    items = list(search.items())
    if not items:
        raise RuntimeError(
            f"no {DEM_COLLECTION} items found for bbox {bbox_key(bbox)}"
        )
    print(f"found {len(items)} DEM tile(s); downloading and mosaicking...")

    arrays = []
    for item in items:
        href = item.assets["data"].href
        da = rioxarray.open_rasterio(href, masked=True).squeeze(drop=True)
        arrays.append(da)

    if len(arrays) == 1:
        merged = arrays[0]
    else:
        from rioxarray.merge import merge_arrays

        merged = merge_arrays(arrays)

    clipped = merged.rio.clip_box(
        minx=bbox.min_lon,
        miny=bbox.min_lat,
        maxx=bbox.max_lon,
        maxy=bbox.max_lat,
    )

    tmp_path = out_path.with_suffix(".part.tif")
    clipped.rio.to_raster(tmp_path, driver="GTiff", compress="deflate", tiled=True)
    tmp_path.replace(out_path)
    print(f"DEM saved: {out_path}")
    return out_path


def _tile_path(z: int, x: int, y: int) -> Path:
    return OSM_TILES_DIR / str(z) / str(x) / f"{y}.pbf"


def _resolve_ofm_tile_template(session: requests.Session) -> str:
    resp = session.get(OFM_TILEJSON_URL, timeout=30)
    resp.raise_for_status()
    tj = resp.json()
    tiles = tj.get("tiles") or []
    if not tiles:
        raise RuntimeError("OpenFreeMap TileJSON has no 'tiles' entry")
    return tiles[0]


def download_osm_tiles(bbox: BoundingBox, zoom: int = OSM_ZOOM, force: bool = False) -> list[mercantile.Tile]:
    tiles = list(
        mercantile.tiles(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, zoom)
    )
    print(f"OSM: {len(tiles)} tile(s) cover bbox at z={zoom}")

    session = requests.Session()
    session.headers.update({"User-Agent": OFM_USER_AGENT})

    needs_fetch = [t for t in tiles if force or not _tile_path(t.z, t.x, t.y).exists()]

    tile_template = None
    if needs_fetch:
        tile_template = _resolve_ofm_tile_template(session)
        print(f"OSM: using tile template {tile_template}")

    fetched = 0
    cached = 0
    empty = 0
    for tile in tiles:
        path = _tile_path(tile.z, tile.x, tile.y)
        if path.exists() and not force:
            cached += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        url = tile_template.format(z=tile.z, x=tile.x, y=tile.y)
        resp = session.get(url, timeout=60)
        if resp.status_code == 404 or resp.status_code == 204 or not resp.content:
            path.write_bytes(b"")
            empty += 1
            continue
        resp.raise_for_status()
        tmp = path.with_suffix(".pbf.part")
        tmp.write_bytes(resp.content)
        tmp.replace(path)
        fetched += 1

    print(f"OSM: fetched={fetched} cached={cached} empty={empty}")
    return tiles


def _decode_tile_bytes(raw: bytes) -> dict:
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return mapbox_vector_tile.decode(raw)


def _tile_pixel_to_lonlat(tile: mercantile.Tile, extent: int):
    west, south, east, north = mercantile.bounds(tile)
    dx = (east - west) / extent
    dy = (north - south) / extent

    def _to_lonlat(x, y, z=None):
        lon = west + x * dx
        lat = south + y * dy
        if z is None:
            return (lon, lat)
        return (lon, lat, z)

    return _to_lonlat


def _feature_matches(cfg: dict, props: dict) -> bool:
    cls = props.get("class")
    inc = cfg.get("include_class")
    if inc is not None and cls not in inc:
        return False
    exc = cfg.get("exclude_class")
    if exc is not None and cls in exc:
        return False
    return True


def process_osm_tiles(bbox: BoundingBox, zoom: int = OSM_ZOOM) -> dict[str, Path]:
    OSM_FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    tiles = list(
        mercantile.tiles(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, zoom)
    )
    from shapely.geometry import box as shp_box

    bbox_geom = shp_box(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat)

    collections: dict[str, list[dict]] = {name: [] for name in LAYER_EXTRACT}

    for tile in tiles:
        path = _tile_path(tile.z, tile.x, tile.y)
        if not path.exists() or path.stat().st_size == 0:
            continue
        decoded = _decode_tile_bytes(path.read_bytes())
        for out_name, cfg in LAYER_EXTRACT.items():
            layer_name = cfg["layer"]
            layer = decoded.get(layer_name)
            if not layer:
                continue
            extent = layer.get("extent", 4096)
            to_lonlat = _tile_pixel_to_lonlat(tile, extent)
            for feat in layer.get("features", []):
                props = feat.get("properties", {}) or {}
                if not _feature_matches(cfg, props):
                    continue
                try:
                    geom = shape(feat["geometry"])
                except Exception:
                    continue
                if geom.is_empty:
                    continue
                geom_ll = shp_transform(to_lonlat, geom)
                if not geom_ll.is_valid:
                    geom_ll = make_valid(geom_ll)
                if geom_ll.is_empty or not geom_ll.intersects(bbox_geom):
                    continue
                try:
                    clipped = geom_ll.intersection(bbox_geom)
                except Exception:
                    continue
                if clipped.is_empty:
                    continue
                collections[out_name].append(
                    {
                        "type": "Feature",
                        "properties": props,
                        "geometry": mapping(clipped),
                    }
                )

    written: dict[str, Path] = {}
    for name, feats in collections.items():
        out_path = OSM_FEATURES_DIR / f"{name}.geojson"
        fc = {"type": "FeatureCollection", "features": feats}
        out_path.write_text(json.dumps(fc))
        written[name] = out_path
        print(f"OSM: {name:16s} {len(feats):6d} features -> {out_path.relative_to(REPO_ROOT)}")
    return written


def overpass_path_for(bbox: BoundingBox) -> Path:
    return OVERPASS_DIR / f"overpass_{bbox_key(bbox)}.json"


def _build_overpass_query(bbox: BoundingBox) -> str:
    s, w, n, e = bbox.min_lat, bbox.min_lon, bbox.max_lat, bbox.max_lon
    bb = f"({s},{w},{n},{e})"
    clauses = []
    for tags in OVERPASS_TAGS.values():
        for k, v in tags:
            clauses.append(f'  node["{k}"="{v}"]{bb};')
            clauses.append(f'  way["{k}"="{v}"]{bb};')
    body = "\n".join(clauses)
    return f"[out:json][timeout:90];\n(\n{body}\n);\nout body geom;\n"


def download_overpass(bbox: BoundingBox, force: bool = False) -> Path:
    OVERPASS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = overpass_path_for(bbox)
    if out_path.exists() and not force:
        print(f"Overpass cache hit: {out_path.relative_to(REPO_ROOT)}")
        return out_path

    query = _build_overpass_query(bbox)
    print(f"Overpass: querying {OVERPASS_ENDPOINT} ...")
    resp = requests.post(
        OVERPASS_ENDPOINT,
        data={"data": query},
        headers={"User-Agent": OFM_USER_AGENT},
        timeout=180,
    )
    resp.raise_for_status()
    payload = resp.json()
    tmp = out_path.with_suffix(".json.part")
    tmp.write_text(json.dumps(payload))
    tmp.replace(out_path)
    n = len(payload.get("elements", []))
    print(f"Overpass: {n} elements -> {out_path.relative_to(REPO_ROOT)}")
    return out_path


def _element_to_feature(el: dict) -> dict | None:
    tags = el.get("tags", {}) or {}
    if el["type"] == "node":
        geom = {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
    elif el["type"] == "way" and el.get("geometry"):
        coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
        if len(coords) < 2:
            return None
        if coords[0] == coords[-1] and len(coords) >= 4:
            geom = {"type": "Polygon", "coordinates": [coords]}
        else:
            geom = {"type": "LineString", "coordinates": coords}
    else:
        return None
    return {
        "type": "Feature",
        "properties": {"osm_id": el.get("id"), "osm_type": el["type"], **tags},
        "geometry": geom,
    }


def process_overpass(bbox: BoundingBox) -> dict[str, Path]:
    OSM_FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    src = overpass_path_for(bbox)
    if not src.exists():
        raise FileNotFoundError(f"missing Overpass cache: {src}")
    payload = json.loads(src.read_text())
    elements = payload.get("elements", [])

    buckets: dict[str, list[dict]] = {name: [] for name in OVERPASS_TAGS}
    for el in elements:
        tags = el.get("tags", {}) or {}
        for name, kvs in OVERPASS_TAGS.items():
            if any(tags.get(k) == v for k, v in kvs):
                feat = _element_to_feature(el)
                if feat is not None:
                    buckets[name].append(feat)
                break

    written: dict[str, Path] = {}
    for name, feats in buckets.items():
        out_path = OSM_FEATURES_DIR / f"overpass_{name}.geojson"
        fc = {"type": "FeatureCollection", "features": feats}
        out_path.write_text(json.dumps(fc))
        written[name] = out_path
        print(f"Overpass: {name:16s} {len(feats):6d} features -> {out_path.relative_to(REPO_ROOT)}")
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate.py",
        description=(
            "Generate a Gazebo world with high-resolution sky and realistic buildings "
            "for a geographic bounding box.\n\n"
            "The bounding box is four comma-separated decimal-degree values in the order:\n"
            "  min_lon,min_lat,max_lon,max_lat\n"
            "which correspond to (west, south, east, north) corners in WGS84 (EPSG:4326).\n"
            "  - min_lon / max_lon: western and eastern longitudes  (-180 .. 180)\n"
            "  - min_lat / max_lat: southern and northern latitudes (-90 .. 90)\n\n"
            "Example: 34.775,32.075,34.785,32.085\n"
            "  This box spans roughly 0.01 deg (about 1.1 km) on each side over central\n"
            "  Israel (Tel Aviv area): west=34.775 E, south=32.075 N, east=34.785 E,\n"
            "  north=32.085 N."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "bbox",
        nargs="?",
        default="34.775,32.075,34.785,32.085",
        help="bounding box as min_lon,min_lat,max_lon,max_lat (default: %(default)s)",
    )
    parser.add_argument(
        "dest",
        nargs="?",
        default=None,
        help=(
            "destination directory for the assembled world "
            "(default: worlds/<bbox_key>/ under the repo root)"
        ),
    )
    parser.add_argument(
        "--world-name",
        default=None,
        help="name embedded in the generated .world file (default: derived from dest dir)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help=(
            "short identifier used as the output directory name and the prefix "
            "for the .world file (default: bbox key). Overrides both dest dir "
            "basename and --world-name unless those are given explicitly."
        ),
    )
    parser.add_argument(
        "--maptiler-key",
        default=None,
        help=(
            "MapTiler API key. Enables the wrapped gazebo_terrain_generator "
            "pipeline which writes a textured world into <dest>/textured/. "
            "Falls back to the MAPTILER_KEY env var."
        ),
    )
    parser.add_argument(
        "--skip-textured",
        action="store_true",
        help="skip the wrapped terrain-generator textured world even if a key is provided",
    )
    parser.add_argument(
        "--textured-zoom",
        type=int,
        default=17,
        help="satellite/OSM tile zoom for the textured world (default: 17)",
    )
    parser.add_argument(
        "--textured-no-buildings",
        action="store_true",
        help="omit buildings.dae from the textured world",
    )
    parser.add_argument(
        "--heightmap-size",
        type=int,
        default=513,
        help="target heightmap PNG side length; snapped to nearest 2^n+1 (default: 513)",
    )
    parser.add_argument(
        "--osm2world-lod",
        type=int,
        default=4,
        help="OSM2World level of detail 0-4 (default: 4)",
    )
    parser.add_argument(
        "--skip-osm2world",
        action="store_true",
        help="skip 3D mesh generation (useful if OSM2World is unavailable)",
    )
    parser.add_argument(
        "--strip-textures",
        action="store_true",
        help=(
            "emit a much smaller untextured mesh: switches OSM2World output "
            "to .obj and removes texture map lines from the .mtl so the "
            "renderer uses per-material diffuse colors instead. Default: off."
        ),
    )
    parser.add_argument(
        "--skip-gba",
        action="store_true",
        help="skip GlobalBuildingAtlas height enrichment",
    )
    parser.add_argument(
        "--force-gba",
        action="store_true",
        help="re-download GBA buildings even if cached",
    )
    parser.add_argument(
        "--force-osm-raw",
        action="store_true",
        help="re-download raw OSM XML even if cached",
    )
    parser.add_argument(
        "--force-dem",
        action="store_true",
        help="re-download the DEM even if a cached file exists",
    )
    parser.add_argument(
        "--force-osm",
        action="store_true",
        help="re-download OSM vector tiles even if cached",
    )
    parser.add_argument(
        "--skip-osm",
        action="store_true",
        help="skip OSM download and processing",
    )
    parser.add_argument(
        "--osm-zoom",
        type=int,
        default=OSM_ZOOM,
        help=f"OpenFreeMap tile zoom to use (default: {OSM_ZOOM})",
    )
    parser.add_argument(
        "--force-overpass",
        action="store_true",
        help="re-query Overpass even if a cached response exists",
    )
    parser.add_argument(
        "--skip-overpass",
        action="store_true",
        help="skip Overpass fetch/processing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        bbox = parse_bbox(args.bbox)
    except ValueError as exc:
        print(f"error: invalid bounding box: {exc}", file=sys.stderr)
        return 2

    lon_c, lat_c = bbox.center
    print(f"bounding box: {bbox.min_lon},{bbox.min_lat},{bbox.max_lon},{bbox.max_lat}")
    print(f"  west={bbox.min_lon}  south={bbox.min_lat}  east={bbox.max_lon}  north={bbox.max_lat}")
    print(f"  size: {bbox.width_deg:.6f} deg lon x {bbox.height_deg:.6f} deg lat")
    print(f"  center: {lon_c:.6f}, {lat_c:.6f}")

    try:
        dem_file = download_dem(bbox, force=args.force_dem)
    except Exception as exc:
        print(f"error: DEM download failed: {exc}", file=sys.stderr)
        return 1
    print(f"DEM ready at: {dem_file.relative_to(REPO_ROOT)}")

    if not args.skip_osm:
        try:
            download_osm_tiles(bbox, zoom=args.osm_zoom, force=args.force_osm)
            process_osm_tiles(bbox, zoom=args.osm_zoom)
        except Exception as exc:
            print(f"error: OSM step failed: {exc}", file=sys.stderr)
            return 1

    if not args.skip_overpass:
        try:
            download_overpass(bbox, force=args.force_overpass)
            process_overpass(bbox)
        except Exception as exc:
            print(f"error: Overpass step failed: {exc}", file=sys.stderr)
            return 1

    # World assembly: destination dir contains everything Gazebo needs.
    name = args.name or bbox_key(bbox)
    dest = Path(args.dest) if args.dest else (REPO_ROOT / "worlds" / name)
    dest = dest.resolve()
    world_name = args.world_name or args.name or dest.name
    print(f"\n=== assembling world '{world_name}' at {dest} ===")

    # 1. Heightmap from cached DEM
    hm_png = dest / "mesh" / "height_map.png"
    try:
        hm_info = heightmap_mod.dem_to_heightmap(
            dem_file, bbox, hm_png, target_size=args.heightmap_size
        )
    except Exception as exc:
        print(f"error: heightmap generation failed: {exc}", file=sys.stderr)
        return 1

    # 2. GBA building heights (optional)
    gba_path = GBA_DIR / f"gba_{bbox_key(bbox)}.geojson"
    if not args.skip_gba:
        try:
            gba_mod.fetch_buildings(bbox, gba_path, force=args.force_gba)
        except Exception as exc:
            print(f"warn: GBA fetch failed, continuing without heights: {exc}", file=sys.stderr)
            gba_path.parent.mkdir(parents=True, exist_ok=True)
            gba_path.write_text('{"type":"FeatureCollection","features":[]}')

    # 3. Raw OSM XML + enrichment
    mesh_path: Path | None = None
    if not args.skip_osm2world:
        raw_osm = OSM_RAW_DIR / f"raw_{bbox_key(bbox)}.osm"
        enriched_osm = dest / "osm" / f"{world_name}.osm"
        try:
            osm_raw_mod.fetch_raw_osm(bbox, raw_osm, force=args.force_osm_raw)
            osm_raw_mod.enrich_with_heights(raw_osm, gba_path, enriched_osm)
        except Exception as exc:
            print(f"error: OSM raw/enrich failed: {exc}", file=sys.stderr)
            return 1

        # 4. OSM2World mesh
        mesh_ext = ".obj" if args.strip_textures else ".glb"
        mesh_path = dest / "mesh" / f"{world_name}{mesh_ext}"
        try:
            osm2world_mod.run(
                enriched_osm,
                mesh_path,
                lod=args.osm2world_lod,
                strip_textures=args.strip_textures,
            )
        except Exception as exc:
            print(f"error: OSM2World failed: {exc}", file=sys.stderr)
            return 1

    # 5. SDF world
    world_file = dest / f"{world_name}.world"
    try:
        world_mod.write_world(
            name=world_name,
            bbox=bbox,
            heightmap=hm_info,
            mesh_path=mesh_path,
            out_path=world_file,
        )
    except Exception as exc:
        print(f"error: world assembly failed: {exc}", file=sys.stderr)
        return 1

    print(f"\ndone: gz sim {world_file}")

    # Optional: wrapped gazebo_terrain_generator pipeline for a textured world.
    maptiler_key = args.maptiler_key or os.environ.get("MAPTILER_KEY")
    if not args.skip_textured and maptiler_key:
        try:
            textured_world = terrain_wrap_mod.build_textured_world(
                name=world_name,
                bbox=bbox,
                dest=dest,
                maptiler_key=maptiler_key,
                sat_zoom=args.textured_zoom,
                include_buildings=not args.textured_no_buildings,
            )
            print(f"textured world: gz sim {textured_world}")
        except Exception as exc:
            print(f"warn: textured world generation failed: {exc}", file=sys.stderr)
    elif not args.skip_textured:
        print("(skip textured world: pass --maptiler-key or set MAPTILER_KEY to enable)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
