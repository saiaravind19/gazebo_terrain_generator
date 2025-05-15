import os


class globalParam:
    PARENT_DIR = os.path.dirname(os.path.abspath(__file__))	
    TEMPFILE_PATH = os.path.join(PARENT_DIR, "temp")
    

    GAZEBO_WORLD_PATH    = None 
    HEIGHTMAP_RESOLUTION = 11  
    DEM_PATH            = None



    # Set the global config
    TEMPORARY_SATELLITE_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)),'temp/gazebo_terrian')
    TEMPLATE_DIR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),'templates')


