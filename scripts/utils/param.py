import os
import tempfile
from pathlib import Path


class GlobalParam:

    # Draw tile borders on aerial.png output for debugging tile grid alignment
    DEBUG_TILE_BORDERS          = False

    # Output base directory (override with GAZEBO_TERRAIN_OUTPUT_PATH env var)
    OUTPUT_BASE_PATH            = os.path.abspath(os.path.expanduser(
                                      os.getenv('GAZEBO_TERRAIN_OUTPUT_PATH',
                                                os.path.join(tempfile.gettempdir(), 'gazebo_terrain_generator'))
                                  ))

    # Path to the SDF/XML world templates directory
    TEMPLATE_DIR_PATH           = str(Path(__file__).resolve().parents[2] / 'templates')

    # DEM zoom cap — MapTiler terrain-rgb-v2 (SRTM-based) has real elevation
    # detail only up to ~zoom 13 (tileset maxzoom is 14)
    DEM_RESOLUTION              = 13

    # Building vector tile zoom — MapTiler OpenMapTiles (v3) serves building
    # footprints with full detail at zoom 15
    DEM_BUILDING_RESOLUTION     = 15

    # Valid Gazebo heightmap sizes (must be 2^n+1)
    VALID_HEIGHTMAP_SIZES       = [257, 513, 1025, 2049, 4097]

