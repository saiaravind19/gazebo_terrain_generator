"""Raw OSM XML fetch (Overpass) and building-height enrichment.

OSM2World consumes .osm/.pbf. Overpass can return XML directly, which we
mutate in-place to attach `height=<meters>` tags to any building way that
lacks explicit height, using the [[gba]] index as the source of truth.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

import requests

from .bbox import BoundingBox
from . import gba as _gba

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
USER_AGENT = "gazebo-world-generator/0.1"


def _query(bbox: BoundingBox) -> str:
    s, w, n, e = bbox.min_lat, bbox.min_lon, bbox.max_lat, bbox.max_lon
    bb = f"({s},{w},{n},{e})"
    # Pull everything visible in the bbox so OSM2World can render buildings,
    # roads, landcover, water, POIs, etc. (nwr = nodes+ways+relations)
    return (
        "[out:xml][timeout:180];\n"
        f"( nwr{bb}; );\n"
        "out body;\n"
        ">;\n"
        "out skel qt;\n"
    )


def fetch_raw_osm(bbox: BoundingBox, out_path: Path, force: bool = False) -> Path:
    if out_path.exists() and not force:
        print(f"OSM raw cache hit: {out_path}")
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"OSM raw: querying {OVERPASS_ENDPOINT} ...")
    resp = requests.post(
        OVERPASS_ENDPOINT,
        data={"data": _query(bbox)},
        headers={"User-Agent": USER_AGENT},
        timeout=300,
    )
    resp.raise_for_status()
    tmp = out_path.with_suffix(out_path.suffix + ".part")
    tmp.write_bytes(resp.content)
    tmp.replace(out_path)
    print(f"OSM raw: {out_path.stat().st_size / 1024:.1f} KiB -> {out_path}")
    return out_path


def _way_polygon(way_el, nodes: dict):
    from shapely.geometry import Polygon

    refs = [nd.get("ref") for nd in way_el.findall("nd")]
    coords = []
    for r in refs:
        n = nodes.get(r)
        if n is None:
            return None
        coords.append(n)
    if len(coords) < 4 or coords[0] != coords[-1]:
        return None
    try:
        poly = Polygon(coords)
    except Exception:
        return None
    if not poly.is_valid or poly.is_empty:
        return None
    return poly


def enrich_with_heights(osm_path: Path, gba_geojson: Path, out_path: Path) -> tuple[int, int]:
    """Rewrite `osm_path` into `out_path` with height= tags on buildings.

    Returns (buildings_seen, heights_injected).
    """
    tree_xml = ET.parse(osm_path)
    root = tree_xml.getroot()

    # Node lookup: id -> (lon, lat)
    nodes: dict[str, tuple[float, float]] = {}
    for n in root.findall("node"):
        nid = n.get("id")
        try:
            lon = float(n.get("lon"))
            lat = float(n.get("lat"))
        except (TypeError, ValueError):
            continue
        nodes[nid] = (lon, lat)

    gba_tree, gba_entries = _gba.load_height_index(gba_geojson)
    if gba_tree is None:
        print("GBA: no building heights available, skipping enrichment")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tree_xml.write(out_path, encoding="utf-8", xml_declaration=True)
        return (0, 0)

    seen = 0
    injected = 0
    for way in root.findall("way"):
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        if "building" not in tags:
            continue
        seen += 1
        if "height" in tags or "building:height" in tags:
            continue
        poly = _way_polygon(way, nodes)
        if poly is None:
            continue
        h = _gba.lookup_height(gba_tree, gba_entries, poly)
        if h is None:
            continue
        ET.SubElement(way, "tag", {"k": "height", "v": f"{h:.1f}"})
        injected += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree_xml.write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"OSM enrich: buildings={seen} heights_injected={injected} -> {out_path}")
    return (seen, injected)
