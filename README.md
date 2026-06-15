# Gazebo Terrain Generator  [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/saiaravind19/gazebo_terrain_generator)

A super easy-to-use tool for generating 3D Gazebo terrain using real-world elevation and satellite data. Draw a polygon on a map, set a spawn location, and get a ready-to-use `.world` file with a textured heightmap and optional 3D buildings.


<video src="https://github.com/user-attachments/assets/42289e73-c66a-4605-85c6-c95d13139d44" controls width="100%"></video>


## Features

- **Real-World Terrain**: Generate 3D Gazebo worlds from actual elevation and satellite imagery of any location on Earth.
- **3D Buildings**: Toggle OSM building footprints extruded as 3D meshes.
- **Configurable Spawn Location**: Drag a marker on the map to set the robot spawn point — GPS coordinates are baked in automatically.
- **Satellite Texture**: Stitched from configurable tile sources (Google, OSM, etc.).
- **High-Precision Heightmap**: 16-bit (~0.008m precision), 8-bit for Fortress compatibility.
- **Downloadable Output**: Get a `.zip` — unzip anywhere and run.


**Supports:** [Gazebo Harmonic](https://gazebosim.org/docs/harmonic/install_ubuntu/) (recommended) · [Gazebo Fortress](https://gazebosim.org/docs/fortress/install_ubuntu/)


## 🔑 Prerequisites

- **Mapbox API Key** — Required for satellite imagery, elevation data, and geocoding. Sign up at [mapbox.com](https://www.mapbox.com/), copy your public token (`pk.eyJ1...`), then paste it in the web UI under **Settings → Mapbox API Key**.
  > Your token is stored in the browser only never server-side.

- **Python package manager (`uv`)** — Required to run the project.

  <details>
  <summary>Linux / macOS</summary>

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

  </details>

  <details>
  <summary>Windows (PowerShell)</summary>

  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

  </details>


## 🛠️ Setup

Clone the repo, install dependencies, and start the server:

```bash
git clone https://github.com/your-org/gazebo_terrain_generator.git
cd gazebo_terrain_generator
uv sync
uv run scripts/server.py
```

Open [http://localhost:8080](http://localhost:8080) in your browser.


## 🚀 Generate a World

1. **Search** — type a place name or GPS coordinates (`lat, lng`)
2. **Draw** — use the polygon tool to outline your area on the map
3. **Set spawn** — drag the pin to where your robot should spawn
4. **Configure** (optional) — open Settings to adjust zoom, tile source, buildings, helipad
5. **Generate** — click **Generate Terrain** and give your world a name
6. **Download** — click **Download World** to get a `.zip`


## ⚙️ Settings

| Setting | Default | Description |
|---|---|---|
| Zoom Level | 17 | Satellite tile zoom — higher means more detail and more tiles |
| Include Buildings | On | Download OSM footprints and extrude as 3D meshes |
| Include Helipad | Off | Adds a helipad at the spawn location |
| Helipad Height | 3.0 m | Height above ground (only relevant when helipad is enabled) |
| Map Tile Source | Google Maps Satellite | Tile provider URL template |
| Parallel Downloads | 4 | Concurrent tile download threads |
| Target Gazebo Version | Harmonic (and above) | Controls heightmap bit depth. Use **Fortress ** for Ignition 6 |

### Output Path

Files are saved to `/tmp/gazebo_terrain_generator/{world_name}/` by default. Override with:

```bash
export GAZEBO_TERRAIN_OUTPUT_PATH=/your/custom/path
```


## 📁 Output Structure

```
{world_name}/
  {world_name}.world    — Gazebo world file (relative URI, no GZ_SIM_RESOURCE_PATH needed)
  model.sdf             — terrain model: heightmap, texture, buildings, helipad
  model.config          — model metadata (enables model:// usage in other worlds)
  mesh/
    height_map.png      — 16-bit grayscale heightmap (8-bit for Fortress)
    aerial.png          — stitched satellite texture
    normal_map.png      — normal map derived from heightmap
    buildings.dae       — 3D building mesh (present only when buildings are enabled and OSM data exists)
```


## 🏁 Running the Generated World

<details>
<summary>Gazebo Harmonic (and above)</summary>

```bash
cd /tmp/gazebo_terrain_generator/{world_name}/
gz sim /tmp/gazebo_terrain_generator/{world_name}/{world_name}.world
```

</details>

<details>
<summary>Gazebo Fortress / Citadel</summary>

```bash
cd /tmp/gazebo_terrain_generator/{world_name}/
ign gazebo /tmp/gazebo_terrain_generator/{world_name}/{world_name}.world
```

</details>

Or unzip the downloaded archive and run with the local path.



## Contributors

Special thanks to [Karinca Robotics](https://karincarobotics.com) and [Polymath Robotics](https://polymathrobotics.com).

## License

BSD 3-Clause License. See [LICENSE](LICENSE) for details.
