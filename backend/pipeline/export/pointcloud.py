from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.pipeline.export.ply import write_ascii_ply, write_gaussian_ply, write_splat
from backend.pipeline.reconstruct.gaussians import points_to_gaussians


def export_pointcloud(
    output_dir: Path,
    xyz: np.ndarray,
    rgb: np.ndarray,
    conf: np.ndarray,
) -> tuple[Path, Path, Path]:
    cloud_path = output_dir / "pointcloud.ply"
    splat_path = output_dir / "gaussians.ply"
    packed = output_dir / "scene.splat"
    write_ascii_ply(cloud_path, xyz, rgb=rgb, confidence=conf)
    gaussians = points_to_gaussians(xyz, rgb)
    write_gaussian_ply(splat_path, gaussians)
    write_splat(packed, xyz, rgb)
    return cloud_path, splat_path, packed
