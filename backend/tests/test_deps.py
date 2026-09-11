from backend.pipeline.reconstruct.deps import check_dependencies, check_openmvs_installation
from backend.pipeline.reconstruct.quality_score import reconstruction_quality_score


def test_dependencies_include_openmvs():
    deps = check_dependencies()
    assert "ffmpeg" in deps
    assert "colmap" in deps
    assert "openmvs" in deps
    assert "denseBackend" in deps


def test_openmvs_detects_bundled_binaries():
    info = check_openmvs_installation()
    assert "installed" in info
    assert "path" in info


def test_quality_score_rejects_fragments():
    score = reconstruction_quality_score(
        {
            "registrationRatio": 0.2,
            "components": 2,
            "meanReprojectionError": 1.5,
            "sparsePoints": 100,
        },
        {"ok": False, "largestFraction": 0.2, "densePoints": 1000},
        {"ok": False, "largestFraction": 0.2},
    )
    assert score["status"] == "FAILED"
    assert score["score"] < 50


def test_quality_score_good():
    score = reconstruction_quality_score(
        {
            "registrationRatio": 0.91,
            "components": 1,
            "meanReprojectionError": 1.4,
            "sparsePoints": 120000,
        },
        {"ok": True, "largestFraction": 0.95, "densePoints": 400000},
        {"ok": True, "largestFraction": 0.97},
    )
    assert score["status"] == "GOOD"
    assert score["score"] >= 75
