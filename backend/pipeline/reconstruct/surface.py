from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from backend.pipeline.export.mesh import heightfield_mesh


SURFACE_FAIL = (
    "3D reconstruction could not produce a reliable surface from this video. "
    "Use a slower walkthrough with overlap, sharp frames, and textured surfaces."
)


def looks_like_voxels(xyz: np.ndarray, faces: np.ndarray) -> bool:
    if len(faces) < 24 or len(xyz) < 8:
        return False
    a, b, c = xyz[faces[:, 0]], xyz[faces[:, 1]], xyz[faces[:, 2]]
    e1, e2 = b - a, c - a
    normals = np.cross(e1, e2)
    nlen = np.linalg.norm(normals, axis=1, keepdims=True)
    nlen[nlen < 1e-12] = 1.0
    normals = np.abs(normals / nlen)
    axis_aligned = normals.max(axis=1) > 0.97
    edge = np.linalg.norm(e1, axis=1)
    finite = edge > 1e-8
    if finite.sum() < 16:
        return False
    sample = edge[finite]
    similar = float(np.std(sample) / (np.median(sample) + 1e-9)) < 0.18
    return bool(axis_aligned.mean() > 0.72 and similar)


def looks_like_spikes(xyz: np.ndarray, faces: np.ndarray) -> bool:
    if len(faces) < 20:
        return True
    a, b, c = xyz[faces[:, 0]], xyz[faces[:, 1]], xyz[faces[:, 2]]
    e1 = np.linalg.norm(b - a, axis=1)
    e2 = np.linalg.norm(c - b, axis=1)
    e3 = np.linalg.norm(a - c, axis=1)
    longest = np.maximum(np.maximum(e1, e2), e3)
    shortest = np.minimum(np.minimum(e1, e2), e3)
    needles = longest > (shortest * 10.0 + 1e-8)
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    med = float(np.median(area[area > 0])) if (area > 0).any() else 0.0
    huge = area > med * 25 if med > 0 else np.zeros(len(faces), dtype=bool)
    return bool(needles.mean() > 0.22 or huge.mean() > 0.18)


def clean_mesh(xyz, rgb, conf, faces):
    if len(faces) == 0 or len(xyz) == 0:
        return xyz, rgb, conf, np.zeros((0, 3), dtype=np.int32)
    faces = faces.astype(np.int32)
    valid = (faces >= 0).all(axis=1) & (faces < len(xyz)).all(axis=1)
    faces = faces[valid]
    if len(faces) == 0:
        return xyz, rgb, conf, faces
    a, b, c = xyz[faces[:, 0]], xyz[faces[:, 1]], xyz[faces[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    e1 = np.linalg.norm(b - a, axis=1)
    e2 = np.linalg.norm(c - b, axis=1)
    e3 = np.linalg.norm(a - c, axis=1)
    longest = np.maximum(np.maximum(e1, e2), e3)
    shortest = np.minimum(np.minimum(e1, e2), e3)
    faces = faces[(area > 1e-12) & (longest <= shortest * 9.0)]
    if len(faces) == 0:
        return xyz, rgb, conf, faces
    ordered = np.sort(faces, axis=1)
    _, uniq = np.unique(ordered, axis=0, return_index=True)
    faces = faces[np.sort(uniq)]
    n = len(xyz)
    ii = np.concatenate([faces[:, 0], faces[:, 0], faces[:, 1]])
    jj = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 2]])
    graph = coo_matrix((np.ones(len(ii)), (ii, jj)), shape=(n, n))
    graph = graph + graph.T
    n_comp, labels = connected_components(graph, directed=False)
    face_lab = labels[faces[:, 0]]
    counts = np.bincount(face_lab, minlength=n_comp)
    floor = max(int(len(faces) * 0.06), 40)
    keep_labs = np.where(counts >= floor)[0]
    if len(keep_labs) == 0:
        keep_labs = np.array([int(np.argmax(counts))], dtype=np.int64)
    faces = faces[np.isin(face_lab, keep_labs)]
    used = np.unique(faces.ravel())
    remap = np.full(len(xyz), -1, dtype=np.int32)
    remap[used] = np.arange(len(used), dtype=np.int32)
    return xyz[used], rgb[used], conf[used], remap[faces]


def ball_pivot_mesh(xyz, rgb, conf, normals: np.ndarray):
    """Local ball-pivoting: only triangles whose vertices share consistent normals."""
    if len(xyz) < 40:
        return xyz, rgb, conf, np.zeros((0, 3), dtype=np.int32)
    tree = cKDTree(xyz)
    nn = tree.query(xyz, k=2)[0][:, 1]
    radius = float(np.median(nn[nn > 0])) * 2.4 if np.any(nn > 0) else 0.05
    radius = max(radius, 1e-4)
    faces = []
    seen = set()
    _, idx = tree.query(xyz, k=min(10, len(xyz)), distance_upper_bound=radius * 2.1)
    for i, neigh in enumerate(idx):
        usable = [int(j) for j in neigh if 0 <= j < len(xyz) and j != i]
        if len(usable) < 2:
            continue
        for a_i in range(len(usable)):
            for b_i in range(a_i + 1, len(usable)):
                j, k = usable[a_i], usable[b_i]
                key = tuple(sorted((i, j, k)))
                if key in seen:
                    continue
                nref = normals[i]
                if abs(float(nref @ normals[j])) < 0.45 or abs(float(nref @ normals[k])) < 0.45:
                    continue
                tri_n = np.cross(xyz[j] - xyz[i], xyz[k] - xyz[i])
                if np.linalg.norm(tri_n) < 1e-10:
                    continue
                if float(tri_n @ nref) < 0:
                    j, k = k, j
                seen.add(key)
                faces.append((i, j, k))
    if not faces:
        return xyz, rgb, conf, np.zeros((0, 3), dtype=np.int32)
    return clean_mesh(xyz, rgb, conf, np.asarray(faces, dtype=np.int32))


def _poisson_open3d(xyz, rgb, conf):
    try:
        import open3d as o3d
    except Exception:
        return None
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(np.clip(rgb.astype(np.float64) / 255.0, 0, 1))
    pcd.estimate_normals()
    pcd.orient_normals_consistent_tangent_plane(16)
    mesh, _ = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=9)
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_non_manifold_edges()
    mesh.remove_unreferenced_vertices()
    if len(mesh.triangles) < 80:
        return None
    verts = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles, dtype=np.int32)
    if len(mesh.vertex_colors):
        colors = np.clip(np.asarray(mesh.vertex_colors) * 255.0, 0, 255).astype(np.uint8)
    else:
        tree = cKDTree(xyz)
        _, nn = tree.query(verts, k=1)
        colors = rgb[nn]
    return clean_mesh(verts, colors, np.ones(len(verts), dtype=np.float32), faces)


def looks_like_fragments(xyz: np.ndarray, faces: np.ndarray) -> bool:
    """Two specks in a huge empty box are not a reconstructed room."""
    if len(faces) < 80:
        return True
    n = len(xyz)
    ii = np.concatenate([faces[:, 0], faces[:, 0], faces[:, 1]])
    jj = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 2]])
    graph = coo_matrix((np.ones(len(ii)), (ii, jj)), shape=(n, n))
    n_comp, labels = connected_components(graph + graph.T, directed=False)
    if n_comp <= 1:
        return False
    sizes = np.bincount(labels, minlength=n_comp)
    big = np.where(sizes >= max(int(n * 0.08), 40))[0]
    if len(big) <= 1:
        return False
    centers = np.array([xyz[labels == k].mean(axis=0) for k in big])
    radii = np.array([np.linalg.norm(xyz[labels == k] - centers[i], axis=1).max() for i, k in enumerate(big)])
    dist = np.linalg.norm(centers[0] - centers[1])
    return bool(dist > (radii[0] + radii[1]) * 2.5)


def validate_triangle_mesh(xyz: np.ndarray, faces: np.ndarray) -> tuple[bool, str]:
    if len(xyz) < 8 or len(faces) < 80:
        return False, "mesh has too few triangles"
    if faces.ndim != 2 or faces.shape[1] != 3:
        return False, "faces are not triangles"
    if looks_like_voxels(xyz, faces):
        return False, "geometry is voxel cubes, not a surface"
    if looks_like_spikes(xyz, faces):
        return False, "geometry is spikes / stretched triangles"
    if looks_like_fragments(xyz, faces):
        return False, "geometry is disconnected fragments, not a scene"
    span = np.ptp(xyz, axis=0)
    if not np.isfinite(span).all() or float(span.max()) <= 1e-6:
        return False, "mesh bounding box is empty"
    return True, "ok"


def reconstruct_surface(
    xyz: np.ndarray,
    rgb: np.ndarray,
    conf: np.ndarray,
    normals: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Surface from a validated dense cloud only. No alpha-shape fallback."""
    if len(xyz) < 200:
        raise RuntimeError(SURFACE_FAIL)

    span = np.ptp(xyz, axis=0)
    terrain_like = float(span[2]) < max(float(span[0]), float(span[1]), 1e-6) * 0.45
    if terrain_like:
        mxyz, mrgb, mconf, faces = heightfield_mesh(xyz, rgb, conf, resolution=220)
        ok, _ = validate_triangle_mesh(mxyz, faces)
        if ok:
            return mxyz, mrgb, mconf, faces

    poisson = _poisson_open3d(xyz, rgb, conf)
    if poisson is not None:
        mxyz, mrgb, mconf, faces = poisson
        ok, _ = validate_triangle_mesh(mxyz, faces)
        if ok:
            return mxyz, mrgb, mconf, faces

    if normals is None or len(normals) != len(xyz):
        tree = cKDTree(xyz)
        _, idx = tree.query(xyz, k=min(16, len(xyz)))
        normals = np.zeros_like(xyz)
        for i, neigh in enumerate(idx):
            pts = xyz[neigh] - xyz[i]
            if len(pts) < 3:
                continue
            _, vecs = np.linalg.eigh(pts.T @ pts)
            normals[i] = vecs[:, 0]
        flip = np.einsum("ij,ij->i", normals, xyz - xyz.mean(0)) < 0
        normals[flip] *= -1

    mxyz, mrgb, mconf, faces = ball_pivot_mesh(xyz, rgb, conf, normals)
    ok, _ = validate_triangle_mesh(mxyz, faces)
    if not ok:
        raise RuntimeError(SURFACE_FAIL)
    return mxyz, mrgb, mconf, faces
