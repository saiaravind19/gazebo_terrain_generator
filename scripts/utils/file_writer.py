import os
from pathlib import Path
from utils.param import GlobalParam

TEMPLATE_DIR = str(Path(__file__).resolve().parents[2] / 'templates')


class FileWriter:

    @staticmethod
    def read_template(template_file_name):
        '''
        Read a template file and return its content as a string.

        Args:
            template_file_name (str): The path to the template file.

        Returns:
            str: The content of the template file.

        '''
        # Open template
        with open(template_file_name, "r") as template_file:
            # Read template
            template_hold_text = template_file.read()
            template = str(template_hold_text)
        return template

    @staticmethod
    def write_world_file(sdf_template, model_name,
                         size_x, size_y, size_z, pose_x, pose_y, pose_z,
                         launch_lat, launch_lon, origin_elevation,
                         include_buildings, output_dir,
                         texture_size=None):
        '''
        Write a Gazebo world file with the terrain model inlined.

        Args:
            sdf_template (str): Template content from gazebo_world_template.sdf.
            model_name (str): Name of the world/model.
            size_x, size_y, size_z (float): Terrain dimensions in meters.
            pose_x, pose_y, pose_z (float): Model pose offsets in meters.
            launch_lat, launch_lon (float): Launch location coordinates.
            origin_elevation (float): Launch location elevation in meters.
            include_buildings (bool): Whether to include the buildings link.
            output_dir (str): Directory to write {model_name}.world into.

        Returns:
            None
        '''
        dae_file = os.path.join(output_dir, 'terrain_data', 'buildings.dae')
        if include_buildings and os.path.isfile(dae_file):
            building_template = FileWriter.read_template(
                os.path.join(TEMPLATE_DIR, 'building_template.sdf')
            )
            buildings_sdf_block = (building_template
                .replace("$MODELNAME$", model_name)
                .replace("$POSX$", str(pose_x))
                .replace("$POSY$", str(pose_y)))
        else:
            buildings_sdf_block = ""

        sdf_template = sdf_template.replace("$MODELNAME$", model_name)
        sdf_template = sdf_template.replace("$SIZEX$", str(size_x))
        sdf_template = sdf_template.replace("$SIZEY$", str(size_y))
        sdf_template = sdf_template.replace("$SIZEZ$", str(size_z))
        sdf_template = sdf_template.replace("$POSX$", str(pose_x))
        sdf_template = sdf_template.replace("$POSY$", str(pose_y))
        sdf_template = sdf_template.replace("$POSZ$", str(pose_z))
        sdf_template = sdf_template.replace("$ORIGIN_LAT$", str(launch_lat))
        sdf_template = sdf_template.replace("$ORIGIN_LONG$", str(launch_lon))
        sdf_template = sdf_template.replace("$ORIGIN_ELEVATION$", str(origin_elevation))
        if GlobalParam.DEBUG_SPHERE:
            debug_sphere_block = FileWriter.read_template(
                os.path.join(TEMPLATE_DIR, 'debug_sphere_template.sdf')
            )
        else:
            debug_sphere_block = ""

        sdf_template = sdf_template.replace("$BUILDING$", buildings_sdf_block)
        sdf_template = sdf_template.replace("$DEBUG_SPHERE$", debug_sphere_block)
        sdf_template = sdf_template.replace("$TEXTURE_SIZE$", str(texture_size if texture_size is not None else max(size_x, size_y)))
        camera_z = round(size_z + pose_z + 200, 1)  # terrain peak in world frame + 200m clearance
        sdf_template = sdf_template.replace("$CAMERA_Z$", str(camera_z))

        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, model_name + ".world"), "w") as f:
            f.write(sdf_template)