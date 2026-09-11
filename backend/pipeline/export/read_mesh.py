from __future__ import annotations

from pathlib import Path

import numpy as np


def read_ascii_mesh_ply(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    n_verts = 0
    n_faces = 0
    has_rgb = False
    header_end = 0
    for i, line in enumerate(lines):
        if line.startswith("element vertex"):
            n_verts = int(line.split()[-1])
        elif line.startswith("element face"):
            n_faces = int(line.split()[-1])
        elif "red" in line:
            has_rgb = True
        elif line.strip() == "end_header":
            header_end = i + 1
            break
    xyz = np.zeros((n_verts, 3), dtype=np.float64)
    rgb = np.full((n_verts, 3), 180, dtype=np.uint8)
    faces = np.zeros((n_faces, 3), dtype=np.int32)
    body = lines[header_end:]
    for i in range(n_verts):
        parts = body[i].split()
        xyz[i] = (float(parts[0]), float(parts[1]), float(parts[2]))
        if has_rgb and len(parts) >= 6:
            rgb[i] = (int(float(parts[3])), int(float(parts[4])), int(float(parts[5])))
    for i in range(n_faces):
        parts = body[n_verts + i].split()
        faces[i] = (int(parts[1]), int(parts[2]), int(parts[3]))
    return xyz, rgb, faces


def read_ascii_cloud_ply(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xyz, rgb, faces = read_ascii_mesh_ply(path)
    conf = np.ones(len(xyz), dtype=np.float32)
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    has_conf = any("confidence" in line for line in lines[:80])
    if has_conf:
        header_end = 0
        n_verts = len(xyz)
        for i, line in enumerate(lines):
            if line.strip() == "end_header":
                header_end = i + 1
                break
        for i in range(n_verts):
            parts = lines[header_end + i].split()
            if len(parts) >= 7:
                conf[i] = float(parts[6])
            elif len(parts) >= 4 and "red" not in "\n".join(lines[:header_end]):
                conf[i] = float(parts[3])
    return xyz, rgb, conf
