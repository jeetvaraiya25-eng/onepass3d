from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def qvec_to_rotmat(qvec: np.ndarray) -> np.ndarray:
    qw, qx, qy, qz = [float(v) for v in qvec]
    return np.array(
        [
            [1 - 2 * qy * qy - 2 * qz * qz, 2 * qx * qy - 2 * qw * qz, 2 * qx * qz + 2 * qw * qy],
            [2 * qx * qy + 2 * qw * qz, 1 - 2 * qx * qx - 2 * qz * qz, 2 * qy * qz - 2 * qw * qx],
            [2 * qx * qz - 2 * qw * qy, 2 * qy * qz + 2 * qw * qx, 1 - 2 * qx * qx - 2 * qy * qy],
        ],
        dtype=np.float64,
    )


def camera_center(qvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    rot = qvec_to_rotmat(qvec)
    return (-rot.T @ np.asarray(tvec, dtype=np.float64)).astype(np.float64)


def list_sparse_models(sparse_dir: Path) -> list[Path]:
    if not sparse_dir.exists():
        return []
    models = []
    for child in sorted(sparse_dir.iterdir()):
        if not child.is_dir():
            continue
        if (child / "images.bin").exists() or (child / "images.txt").exists():
            models.append(child)
    return models


def parse_images_txt(path: Path) -> list[dict]:
    if not path.exists():
        return []
    images = []
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 10:
            continue
        image = {
            "image_id": int(parts[0]),
            "qvec": np.array([float(x) for x in parts[1:5]], dtype=np.float64),
            "tvec": np.array([float(x) for x in parts[5:8]], dtype=np.float64),
            "camera_id": int(parts[8]),
            "name": parts[9],
        }
        image["center"] = camera_center(image["qvec"], image["tvec"])
        if i < len(lines) and not lines[i].startswith("#"):
            i += 1
        images.append(image)
    return images


def parse_points3d_txt(path: Path) -> tuple[int, float]:
    if not path.exists():
        return 0, 0.0
    count = 0
    errors = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 8:
            continue
        count += 1
        errors.append(float(parts[7]))
    mean = float(np.mean(errors)) if errors else 0.0
    return count, mean


def parse_sparse_model(model_dir: Path) -> dict:
    images = parse_images_txt(model_dir / "images.txt")
    n_points, mean_err = parse_points3d_txt(model_dir / "points3D.txt")
    centers = np.array([im["center"] for im in images], dtype=np.float64) if images else np.zeros((0, 3))
    return {
        "model_dir": str(model_dir),
        "registered_images": len(images),
        "images": images,
        "sparse_points": n_points,
        "mean_reprojection_error": mean_err,
        "centers": centers,
    }


def trajectory_stats(centers: np.ndarray) -> dict:
    if len(centers) < 2:
        return {
            "steps": 0,
            "median_step": 0.0,
            "max_step": 0.0,
            "large_jumps": 0,
            "duplicate_poses": 0,
        }
    deltas = np.linalg.norm(np.diff(centers, axis=0), axis=1)
    median = float(np.median(deltas)) if len(deltas) else 0.0
    max_step = float(np.max(deltas)) if len(deltas) else 0.0
    jump_lim = max(median * 12.0, 1e-6)
    large_jumps = int(np.sum(deltas > jump_lim))
    tree = cKDTree(centers)
    dup = 0
    if median > 0:
        pairs = tree.query_pairs(median * 0.02)
        dup = len(pairs)
    return {
        "steps": int(len(deltas)),
        "median_step": median,
        "max_step": max_step,
        "large_jumps": large_jumps,
        "duplicate_poses": dup,
    }


def read_ply(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Read ASCII or binary little-endian PLY (vertices + optional faces/colors)."""
    with Path(path).open("rb") as handle:
        header_lines = []
        while True:
            raw = handle.readline()
            if not raw:
                raise RuntimeError(f"Invalid PLY header: {path}")
            line = raw.decode("ascii", errors="replace").strip()
            header_lines.append(line)
            if line == "end_header":
                break
        fmt = "ascii"
        n_verts = 0
        n_faces = 0
        props: list[tuple[str, str]] = []
        section = ""
        for line in header_lines:
            if line.startswith("format"):
                if "binary_little_endian" in line:
                    fmt = "binary_le"
                elif "binary_big_endian" in line:
                    fmt = "binary_be"
            elif line.startswith("element vertex"):
                section = "vertex"
                n_verts = int(line.split()[-1])
            elif line.startswith("element face"):
                section = "face"
                n_faces = int(line.split()[-1])
            elif line.startswith("property") and section == "vertex":
                parts = line.split()
                if parts[1] == "list" and len(parts) >= 5:
                    props.append((f"list:{parts[2]}:{parts[3]}", parts[-1]))
                else:
                    props.append((parts[1], parts[-1]))
        if fmt == "ascii":
            rest = handle.read().decode("utf-8", errors="replace").splitlines()
            return _parse_ascii_ply(rest, n_verts, n_faces, props)
        return _parse_binary_ply(handle, n_verts, n_faces, props, fmt == "binary_be")


def _dtype_map(name: str, big: bool) -> str:
    endian = ">" if big else "<"
    return {
        "char": f"{endian}b",
        "uchar": f"{endian}B",
        "int8": f"{endian}b",
        "uint8": f"{endian}B",
        "short": f"{endian}h",
        "ushort": f"{endian}H",
        "int": f"{endian}i",
        "uint": f"{endian}I",
        "int32": f"{endian}i",
        "uint32": f"{endian}I",
        "float": f"{endian}f",
        "float32": f"{endian}f",
        "double": f"{endian}d",
        "float64": f"{endian}d",
    }[name]


def _parse_ascii_ply(
    lines: list[str], n_verts: int, n_faces: int, props: list[tuple[str, str]]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    names = [p[1] for p in props]
    xyz = np.zeros((n_verts, 3), dtype=np.float64)
    rgb = np.full((n_verts, 3), 180, dtype=np.uint8)
    faces = np.zeros((n_faces, 3), dtype=np.int32)
    for i in range(n_verts):
        parts = lines[i].split()
        values = {names[j]: parts[j] for j in range(min(len(names), len(parts)))}
        xyz[i] = (float(values["x"]), float(values["y"]), float(values["z"]))
        if "red" in values:
            rgb[i] = (int(float(values["red"])), int(float(values["green"])), int(float(values["blue"])))
    for i in range(n_faces):
        parts = lines[n_verts + i].split()
        if len(parts) >= 4:
            faces[i] = (int(parts[1]), int(parts[2]), int(parts[3]))
    return xyz, rgb, faces


def _read_binary_value(handle, kind: str, big: bool):
    if kind.startswith("list:"):
        _, count_t, item_t = kind.split(":", 2)
        count_raw = handle.read(struct.calcsize(_dtype_map(count_t, big)))
        if not count_raw:
            raise RuntimeError("Truncated binary PLY list count")
        count = struct.unpack(_dtype_map(count_t, big), count_raw)[0]
        item_size = struct.calcsize(_dtype_map(item_t, big))
        handle.read(item_size * int(count))
        return None
    fmt = _dtype_map(kind, big)
    raw = handle.read(struct.calcsize(fmt))
    if len(raw) < struct.calcsize(fmt):
        raise RuntimeError("Truncated binary PLY vertices")
    return struct.unpack(fmt, raw)[0]


def _parse_binary_ply(handle, n_verts: int, n_faces: int, props: list[tuple[str, str]], big: bool):
    xyz = np.zeros((n_verts, 3), dtype=np.float64)
    rgb = np.full((n_verts, 3), 180, dtype=np.uint8)
    names = [p[1] for p in props]
    for i in range(n_verts):
        values = {}
        for kind, name in props:
            values[name] = _read_binary_value(handle, kind, big)
        xyz[i] = (float(values["x"]), float(values["y"]), float(values["z"]))
        if values.get("red") is not None:
            rgb[i] = (int(values["red"]), int(values["green"]), int(values["blue"]))
    faces = np.zeros((n_faces, 3), dtype=np.int32)
    endian = ">" if big else "<"
    for i in range(n_faces):
        count_raw = handle.read(1)
        if not count_raw:
            break
        count = count_raw[0]
        idx_fmt = struct.Struct(endian + ("i" * count))
        raw = handle.read(idx_fmt.size)
        if len(raw) < idx_fmt.size:
            break
        idxs = idx_fmt.unpack(raw)
        if count >= 3:
            faces[i] = (idxs[0], idxs[1], idxs[2])
    return xyz, rgb, faces


def color_mesh_from_cloud(mesh_xyz: np.ndarray, cloud_xyz: np.ndarray, cloud_rgb: np.ndarray) -> np.ndarray:
    if len(mesh_xyz) == 0:
        return np.zeros((0, 3), dtype=np.uint8)
    if len(cloud_xyz) == 0:
        return np.full((len(mesh_xyz), 3), 180, dtype=np.uint8)
    tree = cKDTree(cloud_xyz)
    _, idx = tree.query(mesh_xyz, k=1)
    return cloud_rgb[np.asarray(idx, dtype=np.int64)]


def mesh_components(faces: np.ndarray, n_verts: int) -> dict:
    if n_verts == 0 or len(faces) == 0:
        return {"components": 0, "largest_frac": 0.0, "sizes": []}
    ii, jj = [], []
    for a, b, c in faces:
        for u, v in ((a, b), (b, c), (c, a)):
            ii.extend((int(u), int(v)))
            jj.extend((int(v), int(u)))
    graph = coo_matrix((np.ones(len(ii)), (ii, jj)), shape=(n_verts, n_verts))
    n_comp, labels = connected_components(graph, directed=False)
    sizes = np.bincount(labels).tolist() if n_verts else []
    largest = max(sizes) if sizes else 0
    return {
        "components": int(n_comp),
        "largest_frac": float(largest / max(n_verts, 1)),
        "sizes": sorted((int(s) for s in sizes), reverse=True)[:12],
    }


def cloud_extent(xyz: np.ndarray) -> dict:
    if len(xyz) == 0:
        return {"count": 0, "bbox": [0, 0, 0], "diagonal": 0.0}
    mins = xyz.min(axis=0)
    maxs = xyz.max(axis=0)
    bbox = maxs - mins
    return {
        "count": int(len(xyz)),
        "bbox": [float(bbox[0]), float(bbox[1]), float(bbox[2])],
        "diagonal": float(np.linalg.norm(bbox)),
    }


def statistical_filter(xyz: np.ndarray, rgb: np.ndarray, nb_neighbors: int = 16, std_ratio: float = 2.4):
    if len(xyz) < nb_neighbors + 2:
        return xyz, rgb
    tree = cKDTree(xyz)
    dists, _ = tree.query(xyz, k=min(nb_neighbors + 1, len(xyz)))
    mean = dists[:, 1:].mean(axis=1)
    mu = float(np.mean(mean))
    sigma = float(np.std(mean))
    keep = mean <= mu + std_ratio * sigma
    if int(keep.sum()) < max(50, int(0.35 * len(xyz))):
        return xyz, rgb
    return xyz[keep], rgb[keep]
