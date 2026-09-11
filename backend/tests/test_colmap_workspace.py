from backend.pipeline.reconstruct.colmap.workspace import ColmapWorkspace


def test_workspace_layout_and_stages(tmp_path):
    ws = ColmapWorkspace(tmp_path / "job")
    ws.create()
    assert ws.images.exists()
    assert ws.sparse.exists()
    assert ws.dense.exists()
    assert ws.output.exists()
    assert ws.logs.exists()
    assert ws.metadata_path.exists()
    meta = ws.load_metadata()
    assert meta["stages"]["featureExtraction"] == "pending"
    ws.set_stage("featureExtraction", "completed")
    assert ws.stage_done("featureExtraction")
    assert not ws.stage_done("matching")
