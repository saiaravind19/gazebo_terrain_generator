<div style="display: flex; justify-content: space-between; align-items: center;">
  <h1>Gazebo Terrain Generator</h1>
  <a href="https://deepwiki.com/saiaravind19/gazebo_terrain_generator">
    <img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki">
  </a>
</div>

A super easy-to-use tool for generate 3D Gazebo terrain using real-world elevation and satellite data.


<p align="center">
  <a href="https://www.youtube.com/watch?v=pxL2UF9xl_w">
    <img src="gif/thumnail.png" alt="Project Demo" width="1050"/>
  </a>
</p>

## ✨ Features

- **🌍 Real-World Terrain Generation**: Generate 3D Gazebo worlds using actual elevation data and satellite images of any location on Earth.
- **🎯 Configurable Spawn Location**: Change the spawn location using interactive UI marker within the region of interest
- **⚙️ Configurable Output**: Flexible output paths via environment variables for different deployment scenarios
- **🔧 Customizable Resolution**: Adjustable tile resolution.
- **📦 Complete World Generation**: Generates the entire model with no hassle out of the box

## Supported and Tested Stack

- **[Gazebo Harmonic](https://gazebosim.org/docs/harmonic/install_ubuntu/)**
## 🛠️ Setup Instructions

### Create and Activate Virtual Environment (Recommended)

It's recommended to use a virtual environment to avoid dependency conflicts:

<details>
<summary><strong>For Linux/macOS</strong></summary>

```bash
python3 -m venv venv
source venv/bin/activate
```

</details>

<details>
<summary><strong>For Windows</strong></summary>

```bash
python -m venv venv
venv\Scripts\activate
```

</details>

### Install Requirements

Make sure your virtual environment is active, then install all required Python packages using:
  ```bash
  pip install -r requirements.txt
  ```

## ⚙️ Configuration

### Environment Variables

You can customize where Gazebo worlds are saved using environment variables:

#### **GAZEBO_WORLD_PATH** (Optional)
Controls where generated Gazebo worlds are stored:

```bash
# Use absolute path
export GAZEBO_WORLD_PATH="/opt/gazebo/custom_worlds"

# Use home directory shortcut
export GAZEBO_WORLD_PATH="~/Desktop/my_gazebo_worlds"

# Use relative path (will be converted to absolute)
export GAZEBO_WORLD_PATH="./custom_worlds"
```

**Default Location**: If no environment variable is set, worlds are saved to:
```
gazebo_terrian_generator/output/gazebo_terrian/
```

### File Structure

Generated worlds follow this structure:
```
<GAZEBO_WORLD_PATH>/
├── world_name/
│   ├── model.sdf              # Gazebo model definition
│   ├── model.config           # Model configuration
│   ├── world_name.sdf         # Gazebo world file
│   └── textures/
│       ├── world_name_height_map.tif    # Elevation heightmap
│       └── world_name_aerial.png        # Satellite imagery texture
```

## 🚀 Run Gazebo World Generator

1. **Start the Application**:
    ```bash
    cd gazebo_terrian_generator/scripts
    python server.py
    ```

2. **Access the Web Interface**: 
   Open your web browser and navigate to `http://localhost:8080`

3. **Generate Your World**:
   - Search for any location on Earth
   - Draw a rectangular region of interest
   - Place launch pad marker at desired spawn location
   - Configure settings (zoom level, map source)
   - Click "Generate Terrain" to create your world

4. **Output Location**: 
   Generated worlds are saved to the configured path (see Environment Variables section above)

## 🏁 Spawning Gazebo Worlds

1. **Export the gazebo model path**:
    ```bash
    export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:<path_to_your_gazebo_worlds>
    ```

2. **Run Gazebo with your world**:
    ```bash
    gz sim your_world_name/your_world_name.sdf
    ```

**Note**: Replace `<path_to_your_gazebo_worlds>` with the actual path where your worlds are saved.


## 📋 Sample Worlds Example

Test the installation with provided sample worlds:

1. **Export the sample gazebo model path**:
    ```bash
    export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:~/gazebo_terrian_generator/sample_worlds
    ```

2. **Launch sample world**:
    ```bash
    gz sim prayag/prayag.sdf
    ```

## 🔑 MapBox API Key
A free api key is being used in the repo if it gets limited then please feel free to create your own API key from official [MapBox's website](https://www.mapbox.com/) and replace it in the [`configuration file`](scripts/utils/param.py)

## Important Disclaimer

Downloading map tiles is subject to the terms and conditions of the tile provider. Some providers such as Google Maps have restrictions in place to avoid abuse, therefore before downloading any tiles make sure you understand their TOCs. I recommend not using Google, Bing, and ESRI tiles in any commercial application without their consent.

## License

This project uses work of [Ali Ashraf](https://github.com/AliFlux/MapTilesDownloader).

## Reference
- [Gazebo Heightmap](https://github.com/AS4SR/general_info/wiki/Creating-Heightmaps-for-Gazebo
)
- [Mapbox Dem](https://docs.mapbox.com/data/tilesets/reference/mapbox-terrain-dem-v1/)
