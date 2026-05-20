# Gazebo Terrain Generator — Project Context for AI Assistants

This file captures key architectural decisions, gotchas, and design intent for this project.
It exists so that anyone (human or AI) resuming work has the context needed without re-deriving it.

---

## What this project does

A web-based tool that generates a Gazebo world from real-world satellite and terrain data.
The user draws a polygon on a map, selects a zoom level and launch location, and the tool:
1. Downloads satellite tiles (Mapbox) and DEM tiles (Mapbox Terrain-DEM-v1) for the selected area
2. Stitches satellite tiles into an aerial texture (`aerial.png`)
3. Generates a normalized heightmap (`height_map.png`) — 16-bit for Harmonic, 8-bit for Fortress
4. Generates a normal map (`normal_map.png`) derived from heightmap gradients
5. Optionally downloads and converts OSM buildings to a 3D mesh (`buildings.dae`)
6. Writes a self-contained Gazebo world file (`{model_name}.world`)

The generated world is fully self-contained — no `GAZEBO_MODEL_PATH` or environment variables required.

---

## Output structure

```
/tmp/gazebo_terrain_generator/{model_name}/
  metadata.json          — polygon_vertices, bounds, center, zoom_level, dem_resolution,
                           launch_location, include_buildings, gazebo_version, timestamp
  tiles/[zoom,y,x].png   — flat satellite tiles
  dem/[zoom,y,x].png     — flat DEM tiles (zoom = min(satellite_zoom, 13))
  building_tiles/        — Mapbox vector tile cache for buildings (zoom/x/y.json)
  terrain_data/
    aerial.png            — stitched satellite image (square-padded)
    height_map.png        — normalized heightmap (2^n+1 size); 16-bit PNG for Harmonic, 8-bit for Fortress
    normal_map.png        — normal map derived from heightmap (Sobel gradients)
    buildings.dae         — only if include_buildings=True and OSM data exists
    buildings.geojson     — only if include_buildings=True
  {model_name}.world      — self-contained Gazebo world file
  {model_name}.zip        — created on demand by /download-world endpoint
```

To open: `gz sim /tmp/gazebo_terrain_generator/{model_name}/{model_name}.world`

---

## Tile filename convention

Both satellite and DEM tiles use flat filenames: `[zoom,y,x].png`

- `zoom` = zoom level (integer)
- `y` = tile row (north→south)
- `x` = tile column (west→east)

This is slippy map tile notation. `y` comes before `x` in the filename to match the download sort order.

---

## DEM resolution

`dem_resolution = min(satellite_zoom, 13)`

Mapbox Terrain-DEM-v1 is based on SRTM (~30m ground resolution). Zoom levels above 13 are
interpolated with no real additional detail. Capping at 13 avoids downloading useless data.

---

## Mapbox API key

The Mapbox API key is stored in the browser's `localStorage` under key
`gazebo_terrain_generator_mapbox_key` — separate from main settings so "Revert to Defaults"
never wipes it. The frontend validates it via the Mapbox Styles API before saving.

On each `/download-tile` POST, the frontend sends `mapboxApiKey` alongside the `source` URL template.
The server passes the key to `Utils.download_file()` → `qualify_url()` substitutes `{key}` in the URL.
On each `/end-download` POST, the frontend also sends `mapboxApiKey` for DEM and building downloads.
The server passes it through to `download_dem_data()` and `download_streetmap_data()`.
It is never stored server-side. `param.py` does NOT contain an API key.

The default tile source is Mapbox Satellite (`mapbox.satellite`), using `{key}` as a placeholder
in the URL template. `Utils.qualify_url` handles `{x}`, `{y}`, `{z}`, `{quad}`, and `{key}`.

---

## Coordinate system and Gazebo world origin

`<spherical_coordinates>` in the world file maps a GPS coordinate to Gazebo world position (0, 0, 0).
We set this to the **launch location** (user-selected point), so a robot spawned at world origin
reports the correct GPS coordinates immediately.

The terrain heightmap is geographically centered at `get_true_origin()` — the center of the
downloaded tile bounding rectangle — which is generally NOT the same as the launch location.
The model `<pose>` offsets the terrain so it sits correctly relative to the launch point.

`get_offset(origin_coord, launch_location)` computes that offset in meters (ENU frame:
X=East, Y=North, Z=Up). The model pose applies the negative of this to position the terrain
so the launch point aligns with world (0, 0, 0).

### Heightmap positioning — confirmed gz-sim behavior (live tested)

OGRE2 (visual) and DART/Bullet (collision) use **different** positioning mechanisms for heightmaps:

**Visual (OGRE2):**
- `<heightmap><pos>` is in **world frame** and is the only way to position the visual heightmap
- Model `<pose>` AND link `<pose>` are both **ignored** by OGRE2 for heightmap visuals (confirmed by test)

**Collision (DART/Bullet):**
- `<heightmap><pos>` is **ignored** by DART (changing it has no effect on collisions)
- `<collision><pose>` (standard SDF pose) IS respected by DART

Correct template pattern:
```xml
<collision name="collision">
    <pose>$POSX$ $POSY$ $POSZ$ 0 0 0</pose>   <!-- DART respects this -->
    <geometry><heightmap><pos>0 0 0</pos>...    <!-- DART ignores this -->

<visual name="ground_visual">
    <geometry><heightmap><pos>$POSX$ $POSY$ $POSZ$</pos>...  <!-- OGRE2 respects this -->
```

Do NOT try to use model or link `<pose>` to position heightmaps — both are ignored by OGRE2.

---

## Elevation data — `get_amsl()`

Located in `height_map_generator.py`. Despite the name "AMSL" (Above Mean Sea Level), this is
NOT a mean/average calculation. It's a single-pixel lookup:

1. Map lat/lon to pixel coordinates within the DEM tile
2. Decode the RGB value using Mapbox Terrain-DEM-v1 formula:
   `height = (R × 256² + G × 256 + B) × 0.1 − 10000`

"AMSL" refers to the datum — the returned value is elevation in meters relative to mean sea level.

---

## Normal map

Generated by `HeightmapGenerator.generate_normal_map()` using Sobel gradients.
Strength is scaled by terrain range: `strength = 0.0002 * (terrain_range / 100.0)`.
This prevents over-amplification of SRTM quantization steps on flat terrain.
Saved as `terrain_data/normal_map.png`.

---

## World file templating

Templates live in `templates/`. Python does simple string substitution (`$PLACEHOLDER$` style).
`TEMPLATE_DIR` constant is defined in `file_writer.py` (not in `param.py`).

- `gazebo_world_template.sdf` — full world file with inline `<model>` block and full GUI plugin list
- `building_template.sdf` — buildings model block, injected into `$BUILDING$` when buildings exist on disk
- `debug_sphere_template.sdf` — red debug sphere model, injected into `$DEBUG_SPHERE$` when `GlobalParam.DEBUG_SPHERE=True`

### Placeholders in gazebo_world_template.sdf

| Placeholder | Meaning |
|---|---|
| `$MODELNAME$` | World/model name |
| `$SIZEX$`, `$SIZEY$`, `$SIZEZ$` | Terrain dimensions in meters |
| `$POSX$`, `$POSY$`, `$POSZ$` | Model pose offset in meters (terrain center → launch point) |
| `$ORIGIN_LAT$`, `$ORIGIN_LONG$` | Launch location GPS coordinates |
| `$ORIGIN_ELEVATION$` | Launch location elevation in meters |
| `$TEXTURE_SIZE$` | max(size_x, size_y) — square UV normalization for aerial texture |
| `$CAMERA_Z$` | Initial camera Z = size_z + pose_z + 200 (terrain peak + 200m clearance) |
| `$BUILDING$` | Replaced with building_template.sdf content or empty string |
| `$DEBUG_SPHERE$` | Replaced with debug_sphere_template.sdf content or empty string |

### Camera pose

gz-sim ignores the `<camera>` SDF tag. Camera pose is set via the `MinimalScene` plugin inside
the `<gui>` block: `<camera_pose>0 0 $CAMERA_Z$ 0 1.3963 1.5708</camera_pose>`
(80° nose down, facing north). The full GUI plugin list is embedded in the template to preserve
all standard scene controls (EntityContextMenu, GzSceneManager, InteractiveViewControl, etc.).

### Paths in templates are relative

All `uri` fields use relative paths (`terrain_data/height_map.png`, etc.).
Gazebo resolves these relative to the world file's directory — makes the output portable.

### What NOT to do

Do NOT hardcode SDF/XML blocks as Python strings. All SDF content belongs in template files.

---

## Target simulator versioning (`gazebo_version` / `heightmap_z_resolution`)

The frontend has a "Target Gazebo Version" setting (`gazeboVersion`: `'harmonic'` or `'fortress'`).
At the REST boundary (`server.py`), this string is translated into two typed values:

- `heightmap_z_resolution: int` (65535 for Harmonic, 255 for Fortress) — controls pixel encoding
- `gazebo_version: str` — controls version-specific SDF/GUI template selection

**Rule:** Use the variable that *semantically owns* the decision:
- Pixel encoding decisions → `heightmap_z_resolution`
- GUI plugin template, SDF version-specific features → `gazebo_version`

Do NOT compare `heightmap_z_resolution == 255` to pick a GUI template — those are correlated but
separate concerns. A future simulator (e.g. MuJoCo) might use 8-bit heightmaps but need
Harmonic-style GUI plugins, so conflating them would break extensibility.

`gazebo_version` is written to `metadata.json` for traceability (human-readable record) but is
**not** read back from metadata — it is always passed as a live parameter through the call chain
to keep the system stateless.

---

## Key architectural decisions

### Self-contained world file (no GAZEBO_MODEL_PATH)

The `<model>` block is inlined directly into the world file instead of using
`<include><uri>model://...</uri></include>`. This eliminates the need for `GAZEBO_MODEL_PATH`
or any host environment variables. The world file works standalone.

### Buildings as a separate Gazebo model

The buildings block is wrapped in its own `<model name="$MODELNAME$_buildings">` outside the
terrain model. `$BUILDING$` placeholder is outside the terrain `<model>` block in the template.
`file_writer.py` guards the substitution on `buildings.dae` actually existing on disk.

### Frontend is dumb, server computes geometry

The frontend sends raw `polygonVertices` (array of [lng, lat] pairs) to the server.
The server computes bounds, center, and `dem_resolution`. This avoids multi-user state issues
and keeps geographic logic in one place.

### Polygon selection with gray fill

Tiles are downloaded for all tiles intersecting the selected polygon's bounding rectangle.
Some tiles within the rectangle may be missing (polygon corners). `generate_ortho()` fills
missing tiles with a gray placeholder (RGB 128, 128, 128) to produce a complete rectangular texture.
Aerial texture is square-padded so UV normalization works correctly in OGRE2.

### Progress message queue

`task_status["messages"]` is a list. `progress()` appends to it. `/task-status` endpoint
drains the list on each read (returns messages and resets to []). Frontend logs each message
from the batch. This prevents fast steps from overwriting each other.

### Physics engine

ODE does not behave correctly with heightmaps. The world uses Bullet collision detector via DART:
```xml
<physics name="1ms" type="ignored">
    <dart>
        <collision_detector>bullet</collision_detector>
    </dart>
</physics>
```

---

## Fortress vs Harmonic SDF differences

| Concern | Harmonic (gz-sim 8+) | Fortress (Ignition 6) |
|---|---|---|
| System plugin prefix | `gz-sim-*-system` / `gz::sim::systems::` | `ignition-gazebo-*-system` / `ignition::gazebo::systems::` |
| GUI config tag | `<gz-gui>` | `<ignition-gui>` |
| 3D scene plugin | `MinimalScene` + `GzSceneManager` (two plugins) | `GzScene3D` (single plugin — handles both) |
| World stats GUI plugin | `WorldStats` | `WorldStats` (same — `WorldStatistics` does NOT exist in Fortress) |
| Heightmap bit depth | 16-bit PNG (65535 levels) | 8-bit PNG (255 levels) — Fortress Image.cc misparses 16-bit stride |
| `<sky><clouds>` | Supported | Removed — cloud rendering incomplete in Fortress OGRE2 |
| `<camera_clip>` in MinimalScene/GzScene3D | Respected | Ignored by GzScene3D in Fortress |
| `VisualizationCapabilities` GUI plugin | Exists | Does not exist (introduced in Garden) |

**NavSat gotcha:** The current Harmonic template uses `gz-sim-navsat-system` / `gz::sim::systems::NavSat`.
An earlier version accidentally used the `ignition::` namespace here — that was wrong for Harmonic and was corrected.

**Aerial texture size limit (Fortress):** OGRE-Next 2.2.5 (shipped with Fortress/Ignition 6) has a staging
buffer size limit that causes a hard crash (`GL3PlusDynamicBuffer::map` assertion failure) when the aerial
texture exceeds roughly 16384px in either dimension. At zoom 17 with 512×512 tiles, ~1000 tiles already
produces a ~16000px image. The user-facing fix is to reduce zoom level. No code cap is applied — zoom
level is already the natural knob for controlling output size.

---

## param.py — what belongs there

`param.py` only contains debug/tuning flags that apply globally:
- `DEBUG_TILE_BORDERS` — draw tile borders on aerial.png output
- `DEBUG_SPHERE` — include red debug sphere at world origin

Constants that were moved OUT of param.py:
- `TEMPLATE_DIR` → `file_writer.py` (module-level constant)
- `MAX_HEIGHTMAP_SIZE` → `height_map_generator.py` (module-level constant)
- `BUILDING_TILE_ZOOM` → `building_downloader.py` (module-level constant, value=15)
- `MAPBOX_API_KEY` → frontend localStorage only, never server-side

---

## File map

```
scripts/
  server.py                      — Flask HTTP server, orchestrates the pipeline
  utils/
    param.py                     — Debug flags only: DEBUG_TILE_BORDERS, DEBUG_SPHERE
    dem_tiles_downloader.py      — Downloads Mapbox DEM tiles as flat [zoom,y,x].png
    gazebo_world_generator.py    — OrthoGenerator, GazeboTerrainGenerator; main pipeline entry point
    height_map_generator.py      — Stitches DEM tiles, generates height_map.png (16-bit or 8-bit) + normal_map.png; get_amsl()
    file_writer.py               — read_template(), write_world_file(); TEMPLATE_DIR constant
    buildings_generator.py       — GeoJSON → .dae conversion
    building_downloader.py       — OSM buildings GeoJSON downloader; BUILDING_TILE_ZOOM=15
    maptile_utils.py             — Tile coordinate math (lat/lon ↔ tile x/y/zoom, bounds); class MapTileUtils
    utils.py                     — ConcatImage base class; stitch_flat_tiles()
  frontend/
    index.html                   — Main UI
    js/main.js                   — Mapbox GL JS, polygon draw, launch pin, geocoding search, POST to server
    css/main.css
templates/
  gazebo_world_template.sdf         — Harmonic (gz-sim 8+) world template; gz-sim-* plugins, gz-gui, MinimalScene+GzSceneManager
  gazebo_fortress_world_template.sdf — Fortress (Ignition 6) world template; ignition-gazebo-* plugins, ignition-gui, GzScene3D
  building_template.sdf             — Buildings model block (conditional on buildings.dae existing)
  debug_sphere_template.sdf         — Red debug sphere model (conditional on DEBUG_SPHERE flag)
```