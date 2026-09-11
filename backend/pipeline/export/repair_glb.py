from __future__ import annotations

from pathlib import Path

from backend.pipeline.export.glb import glb_is_valid, write_glb
from backend.pipeline.export.mesh import export_mesh
from backend.pipeline.export.read_mesh import read_ascii_cloud_ply
from backend.pipeline.reconstruct.surface import reconstruct_surface, validate_triangle_mesh


def remesh_job_from_cloud(output_dir: Path) -> Path:
    """Rebuild a real triangle GLB from an existing dense point cloud. No voxel cubes."""
    cloud = output_dir / "pointcloud.ply"
    if not cloud.exists():
        raise FileNotFoundError(f"No pointcloud.ply in {output_dir}")
    xyz, rgb, conf = read_ascii_cloud_ply(cloud)
    mxyz, mrgb, mconf, faces = reconstruct_surface(xyz, rgb, conf)
    ok, why = validate_triangle_mesh(mxyz, faces)
    if not ok:
        raise RuntimeError(why)
    export_mesh(output_dir, mxyz, mrgb, mconf, faces=faces)
    dest = write_glb(output_dir / "model.glb", mxyz, faces, mrgb)
    glb_ok, glb_why = glb_is_valid(dest)
    if not glb_ok:
        raise RuntimeError(glb_why)
    return dest
