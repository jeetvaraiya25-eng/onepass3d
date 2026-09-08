from backend.pipeline.demo.sample_scene import build_sample_site


def test_sample_site_has_metric_points():
    scene = build_sample_site()
    xyz, faces = scene["xyz"], scene["faces"]
    assert len(xyz) > 20000
    assert len(faces) > 40000
    assert scene["meta"]["metric"] is True
    assert int(faces.max()) < len(scene["mesh_xyz"])
