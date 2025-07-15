import os
from pathlib import Path

class globalParam:

    TEMP_PATH                   =  str(Path(__file__).resolve().parents[2] / 'temp')
    OUTPUT_BASE_PATH            = str(Path(__file__).resolve().parents[2] / 'output')

    GAZEBO_WORLD_PATH           = os.path.join(OUTPUT_BASE_PATH,'gazebo_terrian')  
    DEM_RESOLUTION              = 11 
    HEIGHTMAP_RESOLUTION        = 18

    DEM_PATH                    = os.path.join(OUTPUT_BASE_PATH, 'dem')

    # Set the global config
    TEMPORARY_SATELLITE_IMAGE    = os.path.join(TEMP_PATH,'gazebo_terrian')
    TEMPLATE_DIR_PATH            = str(Path(__file__).resolve().parents[2] / 'templates')
    
    # Free Mapbox API Key 
    MAPBOX_API_KEY               = "pk.eyJ1Ijoic2FpYXJhdmluZDE5NDAiLCJhIjoiY2x0d2s5cnVzMDBmeTJpcGYzcTRvenQxOSJ9.QTaaQ1TT1J4AbqlZS-akHA"  
