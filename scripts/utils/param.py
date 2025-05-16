import os
from pathlib import Path

class globalParam:

    TEMP_PATH                   =  str(Path(__file__).resolve().parents[2] / 'temp')
    OUTPUT_BASE_PATH            = str(Path(__file__).resolve().parents[2] / 'output')

    GAZEBO_WORLD_PATH           = os.path.join(OUTPUT_BASE_PATH,'gazebo_terrian')  
    HEIGHTMAP_RESOLUTION        = 10 
    DEM_PATH                    = os.path.join(OUTPUT_BASE_PATH, 'dem')


    # Set the global config
    TEMPORARY_SATELLITE_IMAGE    = os.path.join(TEMP_PATH,'gazebo_terrian')
    TEMPLATE_DIR_PATH            =  str(Path(__file__).resolve().parents[2] / 'templates')

