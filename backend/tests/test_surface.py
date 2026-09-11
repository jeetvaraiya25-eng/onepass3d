import numpy as np

from backend.pipeline.reconstruct.surface import (
    ball_pivot_mesh,
    looks_like_spikes,
    looks_like_voxels,
    validate_triangle_mesh,
)


def _plane(n=24):
    xs, ys = np.meshgrid(np.linspace(0, 1, n), np.linspace(0, 1, n))
    xyz = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(n * n)])
    rgb = np.full((len(xyz), 3), 160, dtype=np.uint8)
    conf = np.ones(len(xyz), dtype=np.float32)
    normals = np.repeat(np.array([[0.0, 0.0, 1.0]]), len(xyz), axis=0)
    return xyz, rgb, conf, normals


def test_voxel_detector_flags_cubes():
    verts = []
    faces = []
    for x in range(4):
        for y in range(4):
            for z in range(4):
                base = len(verts)
                for dx in (0, 1):
                    for dy in (0, 1):
                        for dz in (0, 1):
                            verts.append((x + dx, y + dy, z + dz))
                faces.extend([(base + 0, base + 1, base + 3), (base + 0, base + 3, base + 2)])
    xyz = np.asarray(verts, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int32)
    assert looks_like_voxels(xyz, faces)


def test_spike_detector_flags_needles():
    xyz = np.array([[0, 0, 0], [1, 0, 0], [0.5, 0.01, 40]], dtype=np.float64)
    faces = np.array([[0, 1, 2]] * 30, dtype=np.int32)
    xyz = np.vstack([xyz, np.random.default_rng(0).normal(size=(90, 3)) * 0.01])
    assert looks_like_spikes(xyz[:3], faces[:1]) or looks_like_spikes(xyz[:3], np.repeat(faces[:1], 40, axis=0))


def test_ball_pivot_plane_is_not_voxels():
    xyz, rgb, conf, normals = _plane(16)
    mxyz, mrgb, mconf, faces = ball_pivot_mesh(xyz, rgb, conf, normals)
    assert len(faces) >= 40
    assert not looks_like_voxels(mxyz, faces)
    ok, reason = validate_triangle_mesh(mxyz, faces)
    assert ok, reason
