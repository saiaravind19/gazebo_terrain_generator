import os
import tempfile
from pathlib import Path


class GlobalParam:

    # Draw tile borders on aerial.png output for debugging tile grid alignment
    DEBUG_TILE_BORDERS          = False

    # Include a red debug sphere at world origin in the generated world file
    DEBUG_SPHERE                = False

    # Output base directory (override with GAZEBO_TERRAIN_OUTPUT_PATH env var)
    OUTPUT_BASE_PATH            = os.path.abspath(os.path.expanduser(
                                      os.getenv('GAZEBO_TERRAIN_OUTPUT_PATH',
                                                os.path.join(tempfile.gettempdir(), 'gazebo_terrain_generator'))
                                  ))

    # Path to the SDF/XML world templates directory
    TEMPLATE_DIR_PATH           = str(Path(__file__).resolve().parents[2] / 'templates')

    # DEM zoom cap — Mapbox Terrain-DEM-v1 has real SRTM data only up to zoom 13
    DEM_RESOLUTION              = 13

    # Building vector tile zoom — Mapbox streets-v8 has full footprint detail at zoom 15
    DEM_BUILDING_RESOLUTION     = 15

    # Valid Gazebo heightmap sizes (must be 2^n+1)
    VALID_HEIGHTMAP_SIZES       = [257, 513, 1025, 2049, 4097]
