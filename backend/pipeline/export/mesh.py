from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay

from backend.pipeline.export.ply import write_ascii_ply


def delaunay_mesh(xyz: np.ndarray, max_edge: float | None = None) -> np.ndarray:
    """Fallback 2.5D mesh. Prefer heightfield_mesh for aerial data."""
    if len(xyz) < 8:
        return np.zeros((0, 3), dtype=np.int32)
    xy = xyz[:, :2]
    try:
        tri = Delaunay(xy)
    except Exception:
        return np.zeros((0, 3), dtype=np.int32)
    faces = tri.simplices.astype(np.int32)
    if max_edge is None:
        extent = np.ptp(xyz, axis=0)
        max_edge = float(np.linalg.norm(extent) * 0.06)
    keep = []
    for a, b, c in faces:
        pa, pb, pc = xyz[a], xyz[b], xyz[c]
        e1 = np.linalg.norm(pa - pb)
        e2 = np.linalg.norm(pb - pc)
        e3 = np.linalg.norm(pc - pa)
        dz = max(abs(pa[2] - pb[2]), abs(pb[2] - pc[2]), abs(pc[2] - pa[2]))
        if max(e1, e2, e3) <= max_edge and dz <= max_edge * 0.4:
            keep.append((a, b, c))
    if not keep:
        return np.zeros((0, 3), dtype=np.int32)
    return np.asarray(keep, dtype=np.int32)


def heightfield_mesh(
    xyz: np.ndarray,
    rgb: np.ndarray,
    conf: np.ndarray,
    resolution: int = 160,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """DSM-style mesh: bin XY, median-ish height, fill pinholes, skip real gaps and roof-to-ground cliffs."""
    if len(xyz) < 8:
        return xyz, rgb, conf, np.zeros((0, 3), dtype=np.int32)

    mins = xyz[:, :2].min(axis=0)
    span = np.maximum(xyz[:, :2].max(axis=0) - mins, 1e-6)
    cell = float(np.max(span) / max(resolution, 8))
    nx = int(np.clip(np.ceil(span[0] / cell) + 1, 8, 220))
    ny = int(np.clip(np.ceil(span[1] / cell) + 1, 8, 220))
    cell_x = span[0] / max(nx - 1, 1)
    cell_y = span[1] / max(ny - 1, 1)

    ix = np.clip(((xyz[:, 0] - mins[0]) / cell_x).astype(int), 0, nx - 1)
    iy = np.clip(((xyz[:, 1] - mins[1]) / cell_y).astype(int), 0, ny - 1)

    counts = np.zeros((nx, ny), dtype=np.float64)
    z_sum = np.zeros((nx, ny), dtype=np.float64)
    r_sum = np.zeros((nx, ny), dtype=np.float64)
    g_sum = np.zeros((nx, ny), dtype=np.float64)
    b_sum = np.zeros((nx, ny), dtype=np.float64)
    c_sum = np.zeros((nx, ny), dtype=np.float64)
    np.add.at(counts, (ix, iy), 1)
    np.add.at(z_sum, (ix, iy), xyz[:, 2])
    np.add.at(r_sum, (ix, iy), rgb[:, 0])
    np.add.at(g_sum, (ix, iy), rgb[:, 1])
    np.add.at(b_sum, (ix, iy), rgb[:, 2])
    np.add.at(c_sum, (ix, iy), conf)

    valid = counts > 0
    z = np.full((nx, ny), np.nan)
    r = np.zeros((nx, ny))
    g = np.zeros((nx, ny))
    b = np.zeros((nx, ny))
    c = np.zeros((nx, ny))
    z[valid] = z_sum[valid] / counts[valid]
    r[valid] = r_sum[valid] / counts[valid]
    g[valid] = g_sum[valid] / counts[valid]
    b[valid] = b_sum[valid] / counts[valid]
    c[valid] = c_sum[valid] / counts[valid]

    z, r, g, b, c, valid = _fill_pinholes(z, r, g, b, c, valid, rounds=2)

    finite = np.isfinite(z)
    z_jump = max(cell_x, cell_y, 0.8) * 2.5
    if finite.sum() > 16:
        d0 = np.abs(np.diff(z, axis=0))
        d1 = np.abs(np.diff(z, axis=1))
        samples = []
        if np.isfinite(d0).any():
            samples.append(float(np.nanpercentile(d0, 88)))
        if np.isfinite(d1).any():
            samples.append(float(np.nanpercentile(d1, 88)))
        if samples:
            z_jump = max(float(np.mean(samples)) * 2.2, cell_x * 1.4, 0.6)

    index = np.full((nx, ny), -1, dtype=np.int32)
    verts = []
    colors = []
    confs = []
    n = 0
    for i in range(nx):
        for j in range(ny):
            if not valid[i, j]:
                continue
            index[i, j] = n
            n += 1
            verts.append((mins[0] + i * cell_x, mins[1] + j * cell_y, z[i, j]))
            colors.append((r[i, j], g[i, j], b[i, j]))
            confs.append(c[i, j])

    faces = []
    for i in range(nx - 1):
        for j in range(ny - 1):
            a, b_, c_, d = index[i, j], index[i + 1, j], index[i + 1, j + 1], index[i, j + 1]
            if min(a, b_, c_, d) < 0:
                continue
            zs = [z[i, j], z[i + 1, j], z[i + 1, j + 1], z[i, j + 1]]
            if max(zs) - min(zs) > z_jump:
                continue
            faces.append((a, b_, c_))
            faces.append((a, c_, d))

    if not verts:
        faces = delaunay_mesh(xyz)
        return xyz, rgb, conf, faces

    return (
        np.asarray(verts, dtype=np.float64),
        np.clip(np.asarray(colors), 0, 255).astype(np.uint8),
        np.asarray(confs, dtype=np.float32),
        np.asarray(faces, dtype=np.int32) if faces else np.zeros((0, 3), dtype=np.int32),
    )


def _fill_pinholes(z, r, g, b, c, valid, rounds: int = 2):
    nx, ny = valid.shape
    kernel = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    for _ in range(rounds):
        new_valid = valid.copy()
        z2, r2, g2, b2, c2 = z.copy(), r.copy(), g.copy(), b.copy(), c.copy()
        for i in range(nx):
            for j in range(ny):
                if valid[i, j]:
                    continue
                acc_z = acc_r = acc_g = acc_b = acc_c = 0.0
                n = 0
                for di, dj in kernel:
                    ii, jj = i + di, j + dj
                    if 0 <= ii < nx and 0 <= jj < ny and valid[ii, jj]:
                        acc_z += z[ii, jj]
                        acc_r += r[ii, jj]
                        acc_g += g[ii, jj]
                        acc_b += b[ii, jj]
                        acc_c += c[ii, jj]
                        n += 1
                if n >= 3:
                    new_valid[i, j] = True
                    z2[i, j] = acc_z / n
                    r2[i, j] = acc_r / n
                    g2[i, j] = acc_g / n
                    b2[i, j] = acc_b / n
                    c2[i, j] = acc_c / n
        z, r, g, b, c, valid = z2, r2, g2, b2, c2, new_valid
    return z, r, g, b, c, valid


def write_obj(path: Path, xyz: np.ndarray, faces: np.ndarray, rgb: np.ndarray | None = None) -> None:
    lines = ["# OnePass3D mesh", "o reconstruction"]
    for i, (x, y, z) in enumerate(xyz):
        if rgb is not None:
            rr, gg, bb = rgb[i] / 255.0
            lines.append(f"v {x:.6f} {y:.6f} {z:.6f} {rr:.4f} {gg:.4f} {bb:.4f}")
        else:
            lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
    for a, b, c in faces:
        lines.append(f"f {int(a) + 1} {int(b) + 1} {int(c) + 1}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_mesh(output_dir: Path, xyz: np.ndarray, rgb: np.ndarray, conf: np.ndarray) -> tuple[int, Path, Path]:
    mxyz, mrgb, mconf, faces = heightfield_mesh(xyz, rgb, conf)
    obj_path = output_dir / "mesh.obj"
    ply_path = output_dir / "mesh.ply"
    write_obj(obj_path, mxyz, faces, mrgb)
    write_ascii_ply(ply_path, mxyz, rgb=mrgb, confidence=mconf, faces=faces)
    return int(len(faces)), obj_path, ply_path
