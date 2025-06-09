# Gazebo Terrain Generator

A super easy-to-use tool for generating 3D Gazebo terrain.

<p align="center">
  <a href="https://www.youtube.com/watch?v=pxL2UF9xl_w">
    <img src="gif/thumnail.png" alt="Project Demo" width="1050"/>
  </a>
</p>



## 🛠️ Setup Instructions

### 1. Create and Activate Virtual Environment (Recommended)

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

### 2. Install Requirements

Make sure your virtual environment is active, then install all required Python packages using:

```bash
pip install -r requirements.txt
```


## 3. Run Gazebo world Generator
1. Navigate to the `gazebo_terrian_generator` repository:

   ```bash
   cd gazebo_terrian_generator/scripts
   python server.py
   ```

2. To access application open up your web browser and navigate to `http://localhost:8080`.
3. Gazebo world generated are stored inside `output/gazebo_terrian/` by default. Feel free to change the path defined in `scripts/utils/param.py` as per you choice.

### 4. Spawning the gazebo world
1. Export gazebo resource path based on your gazebo version. Use the table below as reference.

| Gazebo Version |  Resource Path Variable(s)|
|----------------|---------------------------|
| **Ignition** and later | `export IGN_GAZEBO_RESOURCE_PATH=$IGN_GAZEBO_RESOURCE_PATH:~/<your model directory path>` |
| **Harmonic**    | `export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:~/<your model path here>` |



2. Run Gazebo with the required world file.

| Gazebo Version |  Resource Path Variable(s)|
|----------------|---------------------------|
| **Ignition** and later | `ign gazbeo "<path of your  world file>` |
| **Harmonic**    |  `gz sim <path of your  world file file>` |

**Note:** Replace path with your actual path of the .world.


## Spawing sample worlds Example: 

1. Export the gazebo model path

| Gazebo Version |  Resource Path Variable(s)|
|----------------|---------------------------|
| **Ignition** and later | `export IGN_GAZEBO_RESOURCE_PATH=$IGN_GAZEBO_RESOURCE_PATH:~/gazebo_terrian_generator/sample_worlds` |
| **Harmonic**    | `export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:~/gazebo_terrian_generator/sample_worlds` |


2. Spawing gazebo world.

| Gazebo Version |  Resource Path Variable(s)|
|----------------|---------------------------|
| **Ignition** and later | `ign gazebo prayag/prayag.world` |
| **Harmonic**    |  `gz sim prayag/prayag.world` |


## Important Disclaimer

Downloading map tiles is subject to the terms and conditions of the tile provider. Some providers such as Google Maps have restrictions in place to avoid abuse, therefore before downloading any tiles make sure you understand their TOCs. I recommend not using Google, Bing, and ESRI tiles in any commercial application without their consent.

## License

This project uses work of [Ali Ashraf](https://github.com/AliFlux/MapTilesDownloader).
