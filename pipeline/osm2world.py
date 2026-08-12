"""Shell out to OSM2World to convert enriched .osm -> mesh."""
import subprocess
from pathlib import Path

OSM2WORLD_HOME = Path("/opt/OSM2World/latest")
OSM2WORLD_BIN = OSM2WORLD_HOME / "osm2world.sh"

DEFAULT_PROPERTIES = """\
# gazebo_world_generator OSM2World config
# Flat terrain — we drape the mesh on a Gazebo <heightmap> ourselves.
useElevation = false
createTerrain = true
"""


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(DEFAULT_PROPERTIES)
    return path


def _strip_mtl_textures(mesh_path: Path) -> int:
    """For an OSM2World .obj output, drop map_* lines from the sibling .mtl
    so the renderer uses the per-material diffuse color instead of textures.

    Also deletes texture image files referenced by the stripped lines.
    Returns the number of texture references stripped.
    """
    # OSM2World writes either `foo.mtl` or `foo.obj.mtl` depending on version.
    candidates = [
        mesh_path.with_suffix(".mtl"),
        mesh_path.with_suffix(mesh_path.suffix + ".mtl"),
    ]
    mtl = next((p for p in candidates if p.exists()), None)
    if mtl is None:
        return 0
    stripped = 0
    kept_lines: list[str] = []
    removed_files: set[Path] = set()
    for line in mtl.read_text().splitlines():
        s = line.lstrip()
        if s.startswith(("map_", "bump ", "disp ", "decal ", "refl ")):
            stripped += 1
            parts = line.split()
            if len(parts) >= 2:
                candidate = mtl.parent / parts[-1]
                if candidate.is_file():
                    removed_files.add(candidate.resolve())
            continue
        kept_lines.append(line)
    mtl.write_text("\n".join(kept_lines) + "\n")
    for f in removed_files:
        try:
            f.unlink()
        except OSError:
            pass
    print(f"OSM2World: stripped {stripped} texture refs from {mtl.name}, "
          f"deleted {len(removed_files)} texture file(s)")
    return stripped


def run(osm_path: Path, out_mesh: Path, config_path: Path | None = None,
        lod: int = 4, strip_textures: bool = False) -> Path:
    if not OSM2WORLD_BIN.exists():
        raise FileNotFoundError(f"OSM2World not found at {OSM2WORLD_BIN}")
    out_mesh.parent.mkdir(parents=True, exist_ok=True)
    cfg = _write_config(config_path or out_mesh.parent / "osm2world.properties")

    cmd = [
        str(OSM2WORLD_BIN), "convert",
        "-i", str(osm_path),
        "-o", str(out_mesh),
        "--config", str(cfg),
        "--lod", str(lod),
    ]
    print(f"OSM2World: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise RuntimeError(f"OSM2World failed (exit {proc.returncode})")
    if not out_mesh.exists():
        raise RuntimeError(f"OSM2World reported success but {out_mesh} is missing")
    print(f"OSM2World: mesh -> {out_mesh} ({out_mesh.stat().st_size / 1024:.1f} KiB)")
    if strip_textures:
        if out_mesh.suffix.lower() != ".obj":
            print(f"OSM2World: --strip-textures requires .obj output "
                  f"(got {out_mesh.suffix}); skipping strip")
        else:
            _strip_mtl_textures(out_mesh)
    return out_mesh
