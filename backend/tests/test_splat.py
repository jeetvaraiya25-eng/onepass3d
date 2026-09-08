from pathlib import Path

from backend.pipeline.demo.real_splat import SAMPLE_SPLAT, parse_splat


def test_real_splat_parses_if_present():
    if not SAMPLE_SPLAT.exists():
        return
    xyz, rgb, conf = parse_splat(SAMPLE_SPLAT, max_points=2000)
    assert len(xyz) > 500
    assert xyz.shape[1] == 3
    assert rgb.shape == xyz.shape
    assert len(conf) == len(xyz)
