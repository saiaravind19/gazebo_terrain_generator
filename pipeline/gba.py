"""GlobalBuildingAtlas LoD1 WFS client.

Fetches per-building polygons with `height` (meters) from the TUM
GlobalBuildingAtlas public GeoServer instance. No authentication required.
"""
import json
from pathlib import Path

import requests

from .bbox import BoundingBox

BASE = "https://tubvsig-so2sat-vm1.srv.mwn.de"
WFS_URL = f"{BASE}/geoserver/ows"
SESSION_URL = f"{BASE}/viewer-session"
LAYER = "global3D:lod1_global"
# GeoServer instance rejects requests without a browser-like UA / Referer.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "gazebo-world-generator/0.1"
)
REFERER = "https://tubvsig-so2sat-vm1.srv.mwn.de/"


def fetch_buildings(bbox: BoundingBox, out_path: Path, force: bool = False) -> Path:
    if out_path.exists() and not force:
        print(f"GBA cache hit: {out_path}")
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Referer": REFERER,
        "Origin": REFERER.rstrip("/"),
        "Accept": "application/json,*/*",
    })
    sess_resp = session.get(SESSION_URL, timeout=30)
    sess_resp.raise_for_status()
    viewer_session = sess_resp.json().get("viewerSession")
    if not viewer_session:
        raise RuntimeError(f"GBA viewer-session response missing token: {sess_resp.text[:200]}")

    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": LAYER,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": f"{bbox.min_lon},{bbox.min_lat},{bbox.max_lon},{bbox.max_lat},EPSG:4326",
        "viewerSession": viewer_session,
    }
    print(f"GBA: querying {WFS_URL} ...")
    resp = session.get(WFS_URL, params=params, timeout=180)
    resp.raise_for_status()
    payload = resp.json()
    feats = payload.get("features") or []
    tmp = out_path.with_suffix(out_path.suffix + ".part")
    tmp.write_text(json.dumps(payload))
    tmp.replace(out_path)
    print(f"GBA: {len(feats)} buildings -> {out_path}")
    return out_path


def load_height_index(geojson_path: Path):
    """Return (STRtree, list-of-(polygon, height)) for spatial join.

    Returns (None, []) if no usable features.
    """
    from shapely.geometry import shape
    from shapely.strtree import STRtree

    if not geojson_path.exists():
        return None, []
    data = json.loads(geojson_path.read_text())
    entries: list[tuple[object, float]] = []
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        h = props.get("height")
        if h is None:
            continue
        try:
            h = float(h)
        except (TypeError, ValueError):
            continue
        if h <= 0:
            continue
        try:
            geom = shape(feat["geometry"])
        except Exception:
            continue
        if geom.is_empty:
            continue
        entries.append((geom, h))
    if not entries:
        return None, []
    tree = STRtree([g for g, _ in entries])
    return tree, entries


def lookup_height(tree, entries, polygon) -> float | None:
    """Find best GBA height for an OSM building footprint.

    Strategy: pick the GBA polygon with the largest area of overlap with the
    OSM footprint. Falls back to a centroid-contains check.
    """
    if tree is None or polygon.is_empty:
        return None
    # STRtree.query returns indices in shapely 2.x
    idxs = tree.query(polygon)
    best_h = None
    best_area = 0.0
    for i in idxs:
        try:
            i_int = int(i)
        except (TypeError, ValueError):
            continue
        gba_geom, h = entries[i_int]
        try:
            inter = polygon.intersection(gba_geom)
        except Exception:
            continue
        if inter.is_empty:
            continue
        a = inter.area
        if a > best_area:
            best_area = a
            best_h = h
    if best_h is not None:
        return best_h
    # Centroid fallback
    c = polygon.centroid
    idxs = tree.query(c)
    for i in idxs:
        try:
            i_int = int(i)
        except (TypeError, ValueError):
            continue
        gba_geom, h = entries[i_int]
        if gba_geom.contains(c):
            return h
    return None
