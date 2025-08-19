# Gazebo Terrain Generator  [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/saiaravind19/gazebo_terrain_generator) 



A super easy-to-use tool for generate 3D Gazebo terrain using real-world elevation and satellite data.


<p align="center">
  <a href="https://www.youtube.com/embed/TsV34XBntnY?si=zK0TL7pK_RhsNW05">
    <img src="gif/thumnail.png" alt="Project Demo" width="1050"/>
  </a>
</p>

## Features

- **Real-World Terrain Generation**: Generate 3D Gazebo worlds using actual elevation data and satellite images of any location on Earth.
- **Configurable Spawn Location**: Change the spawn location using interactive UI marker within the region of interest
- **Configurable Output**: Flexible output paths via environment variables for different deployment scenarios
- **Customizable Resolution**: Adjustable tile resolution.
- **Complete World Generation**: Generates the entire model with no hassle out of the box

## Supported and Tested Stack

- **[Gazebo Harmonic](https://gazebosim.org/docs/harmonic/install_ubuntu/)**
## 🛠️ Setup Instructions

### Create and Activate Virtual Environment (Recommended)

It's recommended to use a virtual environment to avoid dependency conflicts:

```bash
python3 -m venv terrain_generator
source terrain_generator/bin/activate
```


### Install Requirements

Make sure your virtual environment is active, then install all required Python packages using:
  ```bash
  pip install -r requirements.txt
  ```

## ⚙️ Configuration

### Environment Variables

You can customize where Gazebo Models and World are saved using environment variables:

```bash
export GAZEBO_MODEL_PATH="~/Desktop/gazebo_models"
export GAZEBO_WORLD_PATH="~/Desktop/gazebo_models/worlds"

```

**Default Location**: If no environment variable is set, model and worlds files are saved to:
```
Models saved in **~/gazebo_terrian_generator/output/gazebo_terrain/**
World files in **~/gazebo_terrian_generator/output/gazebo_terrain/worlds**

```

### File Structure

Generated model follow this structure:
```
<GAZEBO_MODEL_PATH>/
├── model_name/
│   ├── model.sdf              # Gazebo model definition
│   ├── model.config           # Model configuration
│   ├── model_name.sdf         # Gazebo world file
│   └── textures/
│       ├── world_name_height_map.tif    # Elevation heightmap
│       └── world_name_aerial.png        # Satellite imagery texture
<GAZEBO_WORLD_PATH>/
├──model_name.sdf         # Gazebo world file
├──model_name_1.sdf       # Gazebo world file
├──model_name_2.sdf       # Gazebo world file

```

## 🚀 Run Gazebo World Generator

1. Navigate to **gazebo_terrian_generator** and start the applciation.
    ```bash
    source terrain_generator/bin/activate
    python server.py
    ```

2. Access the Web Interface: 
   Open your web browser and navigate to `http://localhost:8080`

3. Generate Your World:
   - Search for any location on Earth
   - Draw a rectangular region of interest
   - Place launch pad marker at desired spawn location
   - Configure settings (zoom level, map source)
   - Click "Generate Terrain" to create your world

4. Output Location: 
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

This project is licensed under the **BSD 3-Clause License**.  
See the [LICENSE](LICENSE) file for full details.  

Portions of this project are derived from **MapTilesDownloader** by [Ali Ashraf](https://github.com/AliFlux/MapTilesDownloader),  
which is licensed under the **MIT License**. The MIT-licensed components remain under their original terms.

## Reference
- [Gazebo Heightmap](https://github.com/AS4SR/general_info/wiki/Creating-Heightmaps-for-Gazebo
)
- [Mapbox Dem](https://docs.mapbox.com/data/tilesets/reference/mapbox-terrain-dem-v1/)
