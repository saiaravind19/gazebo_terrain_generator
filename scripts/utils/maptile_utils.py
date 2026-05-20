import mercantile
import os, shutil


class MapTileUtils:
    @staticmethod
    def get_tile_bounds(tile_x, tile_y, zoom):
        """
        Get the latitude/longitude bounds of a tile using the mercantile library.
        Parameters:
        - x (int): Tile number in X direction.
        - y (int): Tile number in Y direction.
        - zoom (int): Zoom level.
        Returns:
        - dict: A dictionary with 'north', 'south', 'east', 'west' latitude/longitude boundaries.
        """
        # Get the bounds of the tile
        bounds = mercantile.bounds(tile_x, tile_y, zoom)

        return {
            "southwest": (bounds.south, bounds.west),  # Southwest corner
            "southeast": (bounds.south, bounds.east),  # Southeast corner
            "northwest": (bounds.north, bounds.west),  # Northwest corner
            "northeast": (bounds.north, bounds.east)  # Northeast corner
        }

    @staticmethod
    def get_max_tilenumber(bound_array, zoom):
        '''
        Get tile numbers for each corner of the bounding box.
        Returns the full rectangular tile range — no square-forcing.
        '''

        sw = (float(bound_array[1]), float(bound_array[0]))
        nw = (float(bound_array[3]), float(bound_array[0]))
        ne = (float(bound_array[3]), float(bound_array[2]))
        se = (float(bound_array[1]), float(bound_array[2]))

        sw_tile_x, sw_tile_y = MapTileUtils.lat_lon_to_tile(sw[0], sw[1], zoom)
        nw_tile_x, nw_tile_y = MapTileUtils.lat_lon_to_tile(nw[0], nw[1], zoom)
        ne_tile_x, ne_tile_y = MapTileUtils.lat_lon_to_tile(ne[0], ne[1], zoom)
        se_tile_x, se_tile_y = MapTileUtils.lat_lon_to_tile(se[0], se[1], zoom)

        return {
            "southwest": (sw_tile_x, sw_tile_y),
            "southeast": (se_tile_x, se_tile_y),
            "northwest": (nw_tile_x, nw_tile_y),
            "northeast": (ne_tile_x, ne_tile_y)
        }

    @staticmethod
    def get_true_boundaries(bound_array: str, zoom):
        '''
        Returns the lat log of the boundaries
        
        '''
        boundaries = MapTileUtils.get_max_tilenumber(bound_array, zoom)
        true_sw = MapTileUtils.get_tile_bounds(boundaries["southwest"][0], boundaries["southwest"][1], zoom)[
            "southwest"]
        true_se = MapTileUtils.get_tile_bounds(boundaries["southeast"][0], boundaries["southeast"][1], zoom)[
            "southeast"]
        true_nw = MapTileUtils.get_tile_bounds(boundaries["northwest"][0], boundaries["northwest"][1], zoom)[
            "northwest"]
        true_ne = MapTileUtils.get_tile_bounds(boundaries["northeast"][0], boundaries["northeast"][1], zoom)[
            "northeast"]

        return {
            "southwest": true_sw,
            "southeast": true_se,
            "northwest": true_nw,
            "northeast": true_ne
        }

    @staticmethod
    def lat_lon_to_tile(lat: float, lon: float, zoom: int):
        """
        Converts latitude and longitude to tile numbers at a given zoom level using mercantile.
        Parameters:
        - lat (float): Latitude in degrees.
        - lon (float): Longitude in degrees.
        - zoom (int): Zoom level.
        Returns:
        - (int, int): Tile x and y numbers.
        """
        # Clamp latitude for Web Mercator projection bounds
        lat = max(min(lat, 85.0511), -85.0511)
        tile = mercantile.tile(lon, lat, zoom)
        return tile.x, tile.y

    @staticmethod
    def dir_check(path: str, remove_existing: bool = False) -> None:
        """
        Check directory existence and create if not exists.

        Args:
            path (str): Path to directory.
            remove_existing (bool): If True, remove existing directory before creating a new one.

        Returns:
            None
        """

        if not os.path.exists(path):
            os.makedirs(path)
        elif remove_existing == True:
            shutil.rmtree(path)
            os.makedirs(path)
