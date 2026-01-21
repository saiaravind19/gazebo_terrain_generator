import os
from pathlib import Path

class globalParam:

    TEMP_PATH                   =  str(Path(__file__).resolve().parents[2] / 'temp')
    OUTPUT_BASE_PATH            = str(Path(__file__).resolve().parents[2] / 'output')

    GAZEBO_MODEL_PATH           = os.path.abspath(os.path.expanduser(os.getenv('GAZEBO_MODEL_PATH', os.path.join(OUTPUT_BASE_PATH,'gazebo_terrain'))))  
    GAZEBO_WORLD_PATH           = os.path.abspath(os.path.expanduser(os.getenv('GAZEBO_WORLD_PATH', os.path.join(OUTPUT_BASE_PATH,'gazebo_terrain/worlds',))))  
    DEM_RESOLUTION              = 13


    DEM_PATH                    = os.path.join(OUTPUT_BASE_PATH, 'dem')
    HELIPAD_MODEL         = "https://fuel.gazebosim.org/1.0/saiaravind19/models/helipad" 
    # Set the global config
    TEMPORARY_SATELLITE_IMAGE    = os.path.join(TEMP_PATH,'gazebo_terrian')
    TEMPLATE_DIR_PATH            = str(Path(__file__).resolve().parents[2] / 'templates')
    
    # Free Mapbox API Key 
    MAPBOX_API_KEY               = "pk.eyJ1IjoiYXJhdmluZDE5NDAiLCJhIjoiY21jNDVyYTM5MDdxYjJqc2FjczA3bTBmeSJ9.kNLCV2BhlN0CRCOBJIpM1A"  
