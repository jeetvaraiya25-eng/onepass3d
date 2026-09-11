import numpy as np

from backend.pipeline.reconstruct.colmap.validator import validate_dense, validate_mesh, validate_sparse


def test_sparse_fails_on_low_registration():
    centers = np.linspace(0, 1, 25 * 3).reshape(25, 3)
    report = validate_sparse(
        total_images=180,
        registered=25,
        sparse_points=120000,
        components=1,
        mean_reproj=1.4,
        centers=centers,
    )
    assert report["ok"] is False
    assert report["status"] == "FAILED"
    assert "Insufficient camera registration" in report["message"]


def test_sparse_fails_on_multiple_components():
    centers = np.linspace(0, 1, 160 * 3).reshape(160, 3)
    report = validate_sparse(
        total_images=180,
        registered=160,
        sparse_points=120000,
        components=2,
        mean_reproj=1.4,
        centers=centers,
    )
    assert report["ok"] is False
    assert "disconnected" in report["message"].lower()


def test_sparse_good():
    centers = np.linspace(0, 4, 164 * 3).reshape(164, 3)
    report = validate_sparse(
        total_images=180,
        registered=164,
        sparse_points=125000,
        components=1,
        mean_reproj=1.4,
        centers=centers,
    )
    assert report["ok"] is True
    assert report["status"] == "GOOD"


def test_dense_rejects_tiny_clusters():
    rng = np.random.default_rng(0)
    chunks = [rng.normal(i * 20, 0.005, size=(40, 3)) for i in range(12)]
    report = validate_dense(np.vstack(chunks), min_points=50)
    assert report["ok"] is False


def test_mesh_rejects_tiny_islands():
    xyz = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [10, 0, 0],
            [11, 0, 0],
            [10, 1, 0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int32)
    report = validate_mesh(xyz, faces)
    assert report["ok"] is False
