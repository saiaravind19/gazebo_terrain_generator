from dataclasses import dataclass


@dataclass
class BoundingBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    @property
    def width_deg(self) -> float:
        return self.max_lon - self.min_lon

    @property
    def height_deg(self) -> float:
        return self.max_lat - self.min_lat

    @property
    def center(self) -> tuple[float, float]:
        return (
            (self.min_lon + self.max_lon) / 2.0,
            (self.min_lat + self.max_lat) / 2.0,
        )

    def key(self) -> str:
        return (
            f"{self.min_lon:.6f}_{self.min_lat:.6f}"
            f"_{self.max_lon:.6f}_{self.max_lat:.6f}"
        )


def parse_bbox(text: str) -> BoundingBox:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        raise ValueError(
            f"expected 4 comma-separated values (min_lon,min_lat,max_lon,max_lat), got {len(parts)}"
        )
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"bounding box values must be numeric: {exc}") from exc

    if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
        raise ValueError("longitude must be within [-180, 180]")
    if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
        raise ValueError("latitude must be within [-90, 90]")
    if min_lon >= max_lon:
        raise ValueError("min_lon must be less than max_lon")
    if min_lat >= max_lat:
        raise ValueError("min_lat must be less than max_lat")

    return BoundingBox(min_lon, min_lat, max_lon, max_lat)
