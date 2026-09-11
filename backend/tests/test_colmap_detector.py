from backend.pipeline.reconstruct.colmap.detector import check_colmap_installation, check_ffmpeg_installation


def test_colmap_detection_returns_required_keys(monkeypatch):
    monkeypatch.setattr("backend.pipeline.reconstruct.colmap.detector.COLMAP_PATH", "")
    monkeypatch.setattr("backend.pipeline.reconstruct.colmap.detector.shutil.which", lambda _name: None)
    info = check_colmap_installation()
    assert info["installed"] is False
    assert info["path"] == ""
    assert info["message"] == "COLMAP is not installed on this machine."
    assert "version" in info


def test_colmap_path_env(monkeypatch, tmp_path):
    binary = tmp_path / "colmap"
    binary.write_text("#!/bin/sh\necho COLMAP 4.2.0\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr("backend.pipeline.reconstruct.colmap.detector.COLMAP_PATH", str(binary))
    monkeypatch.setattr(
        "backend.pipeline.reconstruct.colmap.detector._run_help",
        lambda _path: "COLMAP 4.2.0\npatch_match_stereo\nmesh_texturer\n",
    )
    monkeypatch.setattr("backend.pipeline.reconstruct.colmap.detector._cuda_available", lambda: False)
    info = check_colmap_installation()
    assert info["installed"] is True
    assert info["path"] == str(binary)
    assert info["device"] == "cpu"
    assert info["cuda"] is False


def test_ffmpeg_detection_keys():
    info = check_ffmpeg_installation()
    assert "installed" in info
    assert "path" in info
