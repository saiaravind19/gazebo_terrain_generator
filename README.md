# gazebo-world-generator

Generate a runnable Gazebo (`gz sim`) world for any lat/lon bounding box on Earth — heightmap, buildings, roads, and optional aerial texture.

Two pipelines, one command:

1. **Primary** — Copernicus DEM (30 m) + OpenFreeMap vector tiles + [OSM2World](https://osm2world.org/) meshes, enriched with [GlobalBuildingAtlas](https://github.com/openaerialmap/gbatlas) heights. Zero-config, no API key needed.
2. **Textured (optional)** — wraps a fork of [saiaravind19/gazebo_terrain_generator](https://github.com/saiaravind19/gazebo_terrain_generator) (see [`terrain/README.md`](terrain/README.md)) to add a MapTiler satellite texture plus extruded building footprints as a `buildings.dae`. Requires a [MapTiler](https://www.maptiler.com/cloud/) key.

Each run produces a self-contained directory under `worlds/<name>/` that `gz sim` can open directly.

## Install

Requires Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/). For the textured pipeline you also need a Java runtime plus the OSM2World CLI at `/opt/OSM2World/latest/osm2world.sh` (override the path in `pipeline/osm2world.py`).

```
uv sync
```

## Run

```
# Primary pipeline only
uv run -m pipeline --name my_world 34.775,32.075,34.785,32.085

# Both pipelines (adds worlds/my_world/textured/)
uv run -m pipeline --name my_world --maptiler-key $MAPTILER_KEY 34.775,32.075,34.785,32.085

gz sim worlds/my_world/my_world.world
gz sim worlds/my_world/textured/my_world.world
```

Bounding box is `min_lon,min_lat,max_lon,max_lat` (WGS84). `--name` sets both the output directory and the `.world` file prefix; it defaults to the bbox key.

Useful flags: `--skip-osm2world`, `--skip-overpass`, `--skip-textured`, `--strip-textures`, `--textured-zoom`, `--textured-no-buildings`, `--heightmap-size`. `--help` lists everything.
