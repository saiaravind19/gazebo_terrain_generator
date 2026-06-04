import os
from utils.param import GlobalParam


class FileWriter:

    @staticmethod
    def read_template(template_file_name):
        with open(template_file_name, "r") as template_file:
            return str(template_file.read())

    @staticmethod
    def write_world_file(sdf_template, model_name,
                         size_x, size_y, size_z, pose_x, pose_y, pose_z,
                         launch_lat, launch_lon, origin_elevation,
                         include_buildings, output_dir,
                         texture_size=None, include_helipad=False, helipad_height=5.0):
        '''
        Write model.sdf, model.config, and {model_name}.world into output_dir.

        Buildings are embedded in model.sdf so all mesh URIs resolve relative
        to the model directory regardless of where the world file is launched from.
        Requires GZ_SIM_RESOURCE_PATH to point to the parent of output_dir.

        Args:
            sdf_template (str): Content of the Gazebo world template.
            model_name (str): Name of the world/model.
            size_x, size_y, size_z (float): Terrain dimensions in meters.
            pose_x, pose_y, pose_z (float): Terrain offset from launch point in meters.
            launch_lat, launch_lon (float): Launch location GPS coordinates.
            origin_elevation (float): Launch location elevation in meters AMSL.
            include_buildings (bool): Whether to include the buildings model in model.sdf.
            output_dir (str): Root model directory (flat — all assets live here).
            texture_size (float|None): UV size for aerial texture; defaults to max(size_x, size_y).
            include_helipad (bool): Whether to include a helipad at world origin.
        '''
        texture_size_val = texture_size if texture_size is not None else max(size_x, size_y)
        camera_z = round(size_z + pose_z + 200, 1)

        # --- Buildings block (model.sdf) ---
        dae_file = os.path.join(output_dir, 'buildings.dae')
        if include_buildings and os.path.isfile(dae_file):
            building_template = FileWriter.read_template(
                os.path.join(GlobalParam.TEMPLATE_DIR_PATH, 'building_template.sdf')
            )
            buildings_sdf_block = (building_template
                .replace("$MODELNAME$", model_name)
                .replace("$POSX$", str(pose_x))
                .replace("$POSY$", str(pose_y)))
        else:
            buildings_sdf_block = ""

        # --- Helipad block (model) ---
        if include_helipad:
            helipad_block = (
                f'        <include>\n'
                f'            <name>{model_name}_helipad</name>\n'
                f'            <uri>https://fuel.gazebosim.org/1.0/saiaravind19/models/helipad</uri>\n'
                f'            <pose>0 0 {helipad_height} 0 0 0</pose>\n'
                f'            <static>true</static>\n'
                f'        </include>'
            )
        else:
            helipad_block = ""

        # --- Debug sphere block (world file) ---
        if GlobalParam.DEBUG_SPHERE:
            debug_sphere_block = FileWriter.read_template(
                os.path.join(GlobalParam.TEMPLATE_DIR_PATH, 'debug_sphere_template.sdf')
            )
        else:
            debug_sphere_block = ""

        os.makedirs(output_dir, exist_ok=True)

        # --- Write model.sdf (terrain + buildings) ---
        model_sdf = (FileWriter.read_template(
            os.path.join(GlobalParam.TEMPLATE_DIR_PATH, 'model_template.sdf'))
            .replace("$MODELNAME$", model_name)
            .replace("$SIZEX$", str(size_x))
            .replace("$SIZEY$", str(size_y))
            .replace("$SIZEZ$", str(size_z))
            .replace("$POSX$", str(pose_x))
            .replace("$POSY$", str(pose_y))
            .replace("$POSZ$", str(pose_z))
            .replace("$TEXTURE_SIZE$", str(texture_size_val))
            .replace("$BUILDING$", buildings_sdf_block)
            .replace("$HELIPAD$", helipad_block))
        with open(os.path.join(output_dir, "model.sdf"), "w") as f:
            f.write(model_sdf)

        # --- Write model.config ---
        model_config = (FileWriter.read_template(
            os.path.join(GlobalParam.TEMPLATE_DIR_PATH, 'model_config_template.xml'))
            .replace("$MODELNAME$", model_name))
        with open(os.path.join(output_dir, "model.config"), "w") as f:
            f.write(model_config)

        # --- Write world file ---
        sdf_template = (sdf_template
            .replace("$MODELNAME$", model_name)
            .replace("$ORIGIN_LAT$", str(launch_lat))
            .replace("$ORIGIN_LONG$", str(launch_lon))
            .replace("$ORIGIN_ELEVATION$", str(origin_elevation + (helipad_height if include_helipad else 0)))
            .replace("$CAMERA_Z$", str(camera_z))
            .replace("$DEBUG_SPHERE$", debug_sphere_block))
        with open(os.path.join(output_dir, model_name + ".world"), "w") as f:
            f.write(sdf_template)
