from pathlib import Path

import numpy as np

from backend.pipeline.export.ply import write_ascii_ply
from backend.pipeline.reconstruct.colmap.parser import parse_images_txt, parse_points3d_txt, read_ply


def test_parse_images_and_points(tmp_path: Path):
    images = tmp_path / "images.txt"
    images.write_text(
        """# IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID NAME
1 1 0 0 0 0 0 0 1 frame_000001.jpg
0 0 1
2 1 0 0 0 0.1 0 0 1 frame_000002.jpg
0 0 1
""",
        encoding="utf-8",
    )
    parsed = parse_images_txt(images)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "frame_000001.jpg"

    points = tmp_path / "points3D.txt"
    points.write_text(
        """# POINT3D_ID X Y Z R G B ERROR
1 0 0 0 10 10 10 1.2
2 1 0 0 10 10 10 1.6
""",
        encoding="utf-8",
    )
    count, mean = parse_points3d_txt(points)
    assert count == 2
    assert abs(mean - 1.4) < 1e-6


def test_read_ascii_ply_roundtrip(tmp_path: Path):
    xyz = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    rgb = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255]], dtype=np.uint8)
    faces = np.array([[0, 1, 2]], dtype=np.int32)
    path = tmp_path / "mesh.ply"
    write_ascii_ply(path, xyz, rgb=rgb, faces=faces)
    out_xyz, out_rgb, out_faces = read_ply(path)
    assert len(out_xyz) == 3
    assert len(out_faces) == 1
    assert out_rgb[0, 0] == 255
