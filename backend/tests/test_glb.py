import json
import struct
from pathlib import Path

import numpy as np

from backend.app.config import QUALITY_PRESETS
from backend.pipeline.export.glb import atlas_pixels_usable, glb_is_valid, write_glb


def test_write_glb_roundtrip(tmp_path: Path):
    xyz = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    faces = np.array([[0, 1, 2], [0, 1, 3]], dtype=np.int32)
    rgb = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0]], dtype=np.uint8)
    path = tmp_path / "model.glb"
    write_glb(path, xyz, faces, rgb)
    raw = path.read_bytes()
    assert raw[:4] == b"glTF"
    assert len(raw) > 200
    ok, reason = glb_is_valid(path)
    assert ok, reason
    chunk_len = struct.unpack_from("<I", raw, 12)[0]
    json_chunk = raw[20 : 20 + chunk_len]
    assert b"\x00" not in json_chunk
    json.loads(json_chunk.decode("utf-8"))


def test_noisy_packer_atlas_is_rejected():
    # orange unused packer fill plus confetti islands — the drone_orbit failure mode
    arr = np.zeros((96, 96, 3), dtype=np.uint8)
    arr[:] = (255, 127, 38)
    rng = np.random.default_rng(0)
    arr[:50] = rng.integers(0, 255, size=(50, 96, 3), dtype=np.uint8)
    assert atlas_pixels_usable(arr) is False


def test_a_smooth_photo_atlas_is_kept():
    yy, xx = np.mgrid[0:96, 0:96]
    arr = np.stack(
        [
            np.clip(40 + xx, 0, 255),
            np.clip(90 + yy // 2, 0, 255),
            np.full((96, 96), 70),
        ],
        axis=-1,
    ).astype(np.uint8)
    assert atlas_pixels_usable(arr) is True


def test_no_quality_uses_a_photo_atlas_as_the_default_model():
    assert all(not preset.get("prefer_photo_texture") for preset in QUALITY_PRESETS.values())

