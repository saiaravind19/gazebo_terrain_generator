"""Assemble a Gazebo (gz-sim / Ignition) SDF world.

Structure:
- <heightmap> from the DEM PNG, sized to the bbox in meters
- <mesh> from OSM2World, placed at the bbox-center ENU origin
- <spherical_coordinates> so plugins that need lat/lon can resolve them
"""
from pathlib import Path

from .bbox import BoundingBox
from .heightmap import HeightmapInfo


WORLD_TEMPLATE = """<?xml version="1.0" ?>
<sdf version="1.9">
  <world name="{name}">
    <physics name="1ms" type="ignored">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">
      <render_engine>ogre2</render_engine>
    </plugin>

    <spherical_coordinates>
      <surface_model>EARTH_WGS84</surface_model>
      <world_frame_orientation>ENU</world_frame_orientation>
      <latitude_deg>{lat_c}</latitude_deg>
      <longitude_deg>{lon_c}</longitude_deg>
      <elevation>{elev_c}</elevation>
      <heading_deg>0</heading_deg>
    </spherical_coordinates>

    <light name="sun" type="directional">
      <cast_shadows>true</cast_shadows>
      <pose>0 0 100 0 0 0</pose>
      <diffuse>1 1 1 1</diffuse>
      <specular>0.3 0.3 0.3 1</specular>
      <direction>-0.5 0.3 -1</direction>
    </light>

    <model name="terrain">
      <static>true</static>
      <link name="link">
        <collision name="collision">
          <geometry>
            <heightmap>
              <uri>{heightmap_uri}</uri>
              <size>{sx} {sy} {sz}</size>
              <pos>0 0 0</pos>
            </heightmap>
          </geometry>
        </collision>
        <visual name="visual">
          <geometry>
            <heightmap>
              <uri>{heightmap_uri}</uri>
              <size>{sx} {sy} {sz}</size>
              <pos>0 0 0</pos>
              <use_terrain_paging>false</use_terrain_paging>
              <texture>
                <size>10</size>
                <diffuse>file://media/materials/textures/dirt_diffusespecular.png</diffuse>
                <normal>file://media/materials/textures/flat_normal.png</normal>
              </texture>
            </heightmap>
          </geometry>
        </visual>
      </link>
    </model>

{mesh_model}
  </world>
</sdf>
"""

MESH_MODEL_TEMPLATE = """    <model name="osm2world_scene">
      <static>true</static>
      <link name="link">
        <pose>0 0 {mesh_z} 0 0 0</pose>
        <visual name="visual">
          <geometry>
            <mesh>
              <uri>{mesh_uri}</uri>
            </mesh>
          </geometry>
        </visual>
        <collision name="collision">
          <geometry>
            <mesh>
              <uri>{mesh_uri}</uri>
            </mesh>
          </geometry>
        </collision>
      </link>
    </model>
"""


def write_world(name: str,
                bbox: BoundingBox,
                heightmap: HeightmapInfo,
                mesh_path: Path | None,
                out_path: Path) -> Path:
    lon_c, lat_c = bbox.center
    # Place the mesh at the heightmap center elevation offset from min elevation,
    # since Gazebo heightmap rests at pos.z with pixel 0 = pos.z and pixel max = pos.z + size_z.
    mesh_z = heightmap.center_elev_m - heightmap.min_elev_m

    mesh_model = ""
    if mesh_path is not None:
        mesh_model = MESH_MODEL_TEMPLATE.format(
            mesh_uri=f"file://{mesh_path.resolve()}",
            mesh_z=mesh_z,
        )

    text = WORLD_TEMPLATE.format(
        name=name,
        lat_c=lat_c,
        lon_c=lon_c,
        elev_c=heightmap.center_elev_m,
        heightmap_uri=f"file://{heightmap.png_path.resolve()}",
        sx=heightmap.size_x_m,
        sy=heightmap.size_y_m,
        sz=heightmap.size_z_m,
        mesh_model=mesh_model,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(f"World: {out_path}")
    return out_path
