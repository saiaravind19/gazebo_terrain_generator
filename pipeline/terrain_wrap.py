"""Wrap the standalone gazebo_terrain_generator (under ../terrain/) so it emits
a self-contained textured world into <dest>/textured/ next to the pipeline's
own <dest>/<name>.world.

The old project was frontend-driven: the browser fetched satellite tiles and
posted them to the Flask server, which then stitched them with the DEM and
building footprints into a Gazebo world. Here we replicate that flow headlessly:

  1. Write the metadata.json the terrain code reads on construction.
  2. Fetch MapTiler satellite tiles directly into <textured>/tiles/.
  3. Call the terrain code's DEM + building downloaders (also MapTiler).
  4. Run GazeboTerrainGenerator.generate_gazebo_world() to produce
     <name>.world, mesh/{height_map,normal_map,aerial}.png, mesh/buildings.dae.
  5. Delete the intermediate tile/dem/building_tiles directories.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from multiprocessing.pool import ThreadPool
from pathlib import Path
from urllib import request as urlrequest

from .bbox import BoundingBox

REPO_ROOT = Path(__file__).resolve().parent.parent
TERRAIN_SCRIPTS = REPO_ROOT / "terrain" / "scripts"


def _ensure_terrain_on_path() -> None:
    p = str(TERRAIN_SCRIPTS)
    if p not in sys.path:
        sys.path.insert(0, p)


SAT_TILE_URL = (
    "https://api.maptiler.com/tiles/satellite-v2/{z}/{x}/{y}.jpg?key={key}"
)


def _fetch_sat_tile(args) -> None:
    z, x, y, out_dir, key = args
    out_path = Path(out_dir) / f"[{z},{y},{x}].png"
    if out_path.exists():
        return
    url = SAT_TILE_URL.format(z=z, x=x, y=y, key=key)
    try:
        with urlrequest.urlopen(url, timeout=60) as resp:
            data = resp.read()
    except Exception as e:
        print(f"[sat] skip ({x},{y}): {e}")
        return

    import cv2
    import numpy as np

    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        print(f"[sat] decode failed ({x},{y})")
        return
    cv2.imwrite(str(out_path), img)


def _download_satellite_tiles(bbox: BoundingBox, zoom: int, out_dir: Path, key: str) -> int:
    import mercantile

    out_dir.mkdir(parents=True, exist_ok=True)
    tiles = list(
        mercantile.tiles(bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat, zoom)
    )
    tasks = [(zoom, t.x, t.y, str(out_dir), key) for t in tiles]
    print(f"[sat] fetching {len(tiles)} tiles at z={zoom} ...")
    with ThreadPool(processes=16) as pool:
        pool.map(_fetch_sat_tile, tasks)
    return len(tiles)


def _polygon_from_bbox(bbox: BoundingBox) -> list[list[float]]:
    return [
        [bbox.min_lon, bbox.min_lat],
        [bbox.max_lon, bbox.min_lat],
        [bbox.max_lon, bbox.max_lat],
        [bbox.min_lon, bbox.max_lat],
    ]


def build_textured_world(
    name: str,
    bbox: BoundingBox,
    dest: Path,
    maptiler_key: str,
    sat_zoom: int = 17,
    include_buildings: bool = True,
    gazebo_version: str = "harmonic",
    include_helipad: bool = False,
    helipad_height: float = 3.0,
) -> Path:
    """Run the terrain project headlessly into <dest>/textured/.

    Returns the path to the generated .world file.
    """
    _ensure_terrain_on_path()

    from utils.building_downloader import download_streetmap_data
    from utils.dem_tiles_downloader import download_dem_data
    from utils.gazebo_world_generator import GazeboTerrainGenerator
    from utils.height_map_generator import HeightmapGenerator
    from utils.maptile_utils import MapTileUtils
    from utils.param import GlobalParam

    tile_path = (dest / "textured").resolve()
    if tile_path.exists():
        shutil.rmtree(tile_path)
    tile_path.mkdir(parents=True)

    polygon_vertices = _polygon_from_bbox(bbox)
    lon_c, lat_c = bbox.center
    launch_location = [lon_c, lat_c]

    dem_resolution = min(sat_zoom, GlobalParam.DEM_RESOLUTION)
    heightmap_z_resolution = 255 if gazebo_version == "fortress" else 65535

    metadata = {
        "name": name,
        "polygon_vertices": polygon_vertices,
        "bounds": f"{bbox.min_lon},{bbox.min_lat},{bbox.max_lon},{bbox.max_lat}",
        "center": f"{lon_c},{lat_c}",
        "zoom_level": sat_zoom,
        "dem_resolution": dem_resolution,
        "launch_location": f"{lon_c},{lat_c}",
        "include_buildings": include_buildings,
        "include_helipad": include_helipad,
        "helipad_height": helipad_height,
        "gazebo_version": gazebo_version,
    }
    (tile_path / "metadata.json").write_text(json.dumps(metadata, indent=2))

    true_boundaries = MapTileUtils.get_true_boundaries(
        [str(bbox.min_lon), str(bbox.min_lat), str(bbox.max_lon), str(bbox.max_lat)],
        sat_zoom,
    )

    tiles_dir = tile_path / "tiles"
    _download_satellite_tiles(bbox, sat_zoom, tiles_dir, maptiler_key)

    dem_dir = tile_path / "dem"
    print("[terrain] downloading DEM tiles ...")
    download_dem_data(true_boundaries, str(dem_dir), dem_resolution, maptiler_key)

    if include_buildings:
        print("[terrain] downloading building footprints ...")
        download_streetmap_data(
            true_boundaries,
            str(tile_path / "building_tiles"),
            str(tile_path),
            api_key=maptiler_key,
            polygon_vertices=polygon_vertices,
        )

    target_heightmap_size = _compute_auto_heightmap_size(
        bbox, dem_resolution, MapTileUtils, HeightmapGenerator
    )
    (tile_path / "metadata.json").write_text(
        json.dumps({**metadata, "target_heightmap_size": target_heightmap_size}, indent=2)
    )

    # Terrain code derives model_name from tile_path basename; that basename is
    # "textured", not <name>. Rename after generation so the .world file matches.
    print(f"[terrain] generating world (model_name=textured) ...")
    generator = GazeboTerrainGenerator(
        str(tile_path),
        include_buildings,
        heightmap_z_resolution,
        gazebo_version,
        target_heightmap_size,
        include_helipad=include_helipad,
        helipad_height=helipad_height,
    )
    generator.generate_gazebo_world()

    produced = tile_path / f"{tile_path.name}.world"
    final_world = tile_path / f"{name}.world"
    if produced.exists() and produced != final_world:
        produced.replace(final_world)

    # Fix model.config reference to match the renamed world name.
    cfg = tile_path / "model.config"
    if cfg.exists():
        cfg.write_text(cfg.read_text().replace(f"{tile_path.name}.world", f"{name}.world"))

    for cleanup in ("tiles", "dem", "building_tiles"):
        p = tile_path / cleanup
        if p.is_dir():
            shutil.rmtree(p)
    for cleanup in ("buildings.geojson", "metadata.json"):
        p = tile_path / cleanup
        if p.is_file():
            p.unlink()

    print(f"[terrain] wrote {final_world}")
    return final_world


def _compute_auto_heightmap_size(bbox: BoundingBox, dem_resolution: int, MapTileUtils, HeightmapGenerator) -> int:
    dem_tiles = MapTileUtils.get_max_tilenumber(
        [str(bbox.min_lon), str(bbox.min_lat), str(bbox.max_lon), str(bbox.max_lat)],
        dem_resolution,
    )
    x_count = dem_tiles["northeast"][0] - dem_tiles["northwest"][0] + 1
    y_count = dem_tiles["southwest"][1] - dem_tiles["northwest"][1] + 1
    natural_max = max(x_count * 512, y_count * 512)
    return HeightmapGenerator.get_nearest_map_size(natural_max)
