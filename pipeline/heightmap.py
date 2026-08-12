"""Convert a Copernicus DEM GeoTIFF into a Gazebo-ready heightmap PNG."""
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rioxarray  # noqa: F401 — activates .rio accessor

from .bbox import BoundingBox

# Gazebo's <heightmap> requires side length = 2^n + 1
VALID_SIZES = [129, 257, 513, 1025, 2049, 4097]


@dataclass
class HeightmapInfo:
    png_path: Path
    size_px: int          # side length of PNG (2^n + 1)
    size_x_m: float       # world extent E-W in meters (matches bbox width)
    size_y_m: float       # world extent N-S in meters (matches bbox height)
    min_elev_m: float
    max_elev_m: float
    center_elev_m: float

    @property
    def size_z_m(self) -> float:
        return max(self.max_elev_m - self.min_elev_m, 1.0)


def _nearest_valid_size(dim: int) -> int:
    if dim <= VALID_SIZES[0]:
        return VALID_SIZES[0]
    if dim >= VALID_SIZES[-1]:
        return VALID_SIZES[-1]
    n = math.log2(max(dim - 1, 1))
    lower = (2 ** int(math.floor(n))) + 1
    upper = (2 ** int(math.ceil(n))) + 1
    return lower if abs(dim - lower) <= abs(dim - upper) else upper


def _bbox_meters(bbox: BoundingBox) -> tuple[float, float]:
    """Approximate ENU extents in meters using WGS84 ellipsoid formulas."""
    lat_c = math.radians((bbox.min_lat + bbox.max_lat) / 2.0)
    m_per_deg_lat = 111132.92 - 559.82 * math.cos(2 * lat_c) + 1.175 * math.cos(4 * lat_c)
    m_per_deg_lon = 111412.84 * math.cos(lat_c) - 93.5 * math.cos(3 * lat_c)
    return (bbox.width_deg * m_per_deg_lon, bbox.height_deg * m_per_deg_lat)


def dem_to_heightmap(dem_tif: Path, bbox: BoundingBox, out_png: Path,
                     target_size: int = 513) -> HeightmapInfo:
    import xarray as xr  # noqa: F401
    from PIL import Image

    da = rioxarray.open_rasterio(dem_tif, masked=True).squeeze(drop=True)
    # Clip precisely to the bbox and reproject-align if needed
    da = da.rio.clip_box(
        minx=bbox.min_lon, miny=bbox.min_lat,
        maxx=bbox.max_lon, maxy=bbox.max_lat,
    )

    arr = np.array(da.values, dtype=np.float32)
    # Fill NaNs with the nearest finite value or 0
    if np.isnan(arr).any():
        finite = arr[np.isfinite(arr)]
        fill = float(finite.mean()) if finite.size else 0.0
        arr = np.where(np.isfinite(arr), arr, fill)

    min_e = float(arr.min())
    max_e = float(arr.max())
    rng = max(max_e - min_e, 1.0)

    # Normalize to 16-bit
    norm = ((arr - min_e) / rng * 65535.0).clip(0, 65535).astype(np.uint16)

    size = _nearest_valid_size(target_size)

    img = Image.fromarray(norm, mode="I;16")
    img = img.resize((size, size), Image.BILINEAR)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, format="PNG")

    size_x_m, size_y_m = _bbox_meters(bbox)
    # Elevation of the bbox center pixel (used as the world origin altitude)
    cy, cx = norm.shape[0] // 2, norm.shape[1] // 2
    center_norm = float(norm[cy, cx])
    center_elev = min_e + (center_norm / 65535.0) * rng

    info = HeightmapInfo(
        png_path=out_png,
        size_px=size,
        size_x_m=size_x_m,
        size_y_m=size_y_m,
        min_elev_m=min_e,
        max_elev_m=max_e,
        center_elev_m=center_elev,
    )
    print(f"Heightmap: {size}x{size}px, {size_x_m:.1f}x{size_y_m:.1f}m, "
          f"elev {min_e:.1f}..{max_e:.1f}m -> {out_png}")
    return info
