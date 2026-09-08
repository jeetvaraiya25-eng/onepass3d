from __future__ import annotations

from pathlib import Path

import numpy as np


def write_ascii_ply(
    path: Path,
    xyz: np.ndarray,
    rgb: np.ndarray | None = None,
    confidence: np.ndarray | None = None,
    faces: np.ndarray | None = None,
) -> None:
    n = len(xyz)
    fcount = 0 if faces is None else len(faces)
    props = ["property float x", "property float y", "property float z"]
    if rgb is not None:
        props += ["property uchar red", "property uchar green", "property uchar blue"]
    if confidence is not None:
        props += ["property float confidence"]
    header = [
        "ply",
        "format ascii 1.0",
        f"element vertex {n}",
        *props,
    ]
    if fcount:
        header += ["element face {0}".format(fcount), "property list uchar int vertex_indices"]
    header.append("end_header")
    lines = header
    for i in range(n):
        x, y, z = xyz[i]
        row = f"{x:.6f} {y:.6f} {z:.6f}"
        if rgb is not None:
            r, g, b = [int(v) for v in rgb[i]]
            row += f" {r} {g} {b}"
        if confidence is not None:
            row += f" {float(confidence[i]):.4f}"
        lines.append(row)
    if faces is not None:
        for tri in faces:
            lines.append(f"3 {int(tri[0])} {int(tri[1])} {int(tri[2])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_splat(path: Path, xyz: np.ndarray, rgb: np.ndarray, radius: float | None = None) -> None:
    """Write antimatter15 .splat (32 bytes / Gaussian) from a colored point cloud."""
    n = len(xyz)
    if n == 0:
        path.write_bytes(b"")
        return
    extent = float(np.ptp(xyz.astype(np.float64), axis=0).max())
    if radius is None:
        radius = float(max(extent / max((n ** (1.0 / 3.0)) * 9.0, 1.0), 1e-4))
    pos = np.ascontiguousarray(xyz, dtype=np.float32)
    scales = np.ascontiguousarray(np.full((n, 3), np.float32(radius)))
    color = np.zeros((n, 4), dtype=np.uint8)
    color[:, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    color[:, 3] = 255
    rot = np.zeros((n, 4), dtype=np.uint8)
    rot[:, 0] = 255
    out = np.empty((n, 32), dtype=np.uint8)
    out[:, 0:12] = pos.view(np.uint8).reshape(n, 12)
    out[:, 12:24] = scales.view(np.uint8).reshape(n, 12)
    out[:, 24:28] = color
    out[:, 28:32] = rot
    path.write_bytes(out.tobytes())


def write_gaussian_ply(path: Path, gaussians: dict[str, np.ndarray]) -> None:
    xyz = gaussians["xyz"]
    n = len(xyz)
    header = [
        "ply",
        "format ascii 1.0",
        f"element vertex {n}",
        "property float x",
        "property float y",
        "property float z",
        "property float f_dc_0",
        "property float f_dc_1",
        "property float f_dc_2",
        "property float opacity",
        "property float scale_0",
        "property float scale_1",
        "property float scale_2",
        "property float rot_0",
        "property float rot_1",
        "property float rot_2",
        "property float rot_3",
        "end_header",
    ]
    lines = header
    f_dc = gaussians["f_dc"]
    opacity = gaussians["opacity"]
    scale = gaussians["scale"]
    rot = gaussians["rot"]
    for i in range(n):
        x, y, z = xyz[i]
        lines.append(
            f"{x:.6f} {y:.6f} {z:.6f} "
            f"{f_dc[i, 0]:.6f} {f_dc[i, 1]:.6f} {f_dc[i, 2]:.6f} "
            f"{opacity[i]:.6f} "
            f"{scale[i, 0]:.6f} {scale[i, 1]:.6f} {scale[i, 2]:.6f} "
            f"{rot[i, 0]:.6f} {rot[i, 1]:.6f} {rot[i, 2]:.6f} {rot[i, 3]:.6f}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
