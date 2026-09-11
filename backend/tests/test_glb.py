import json
import struct
from pathlib import Path

import numpy as np

from backend.pipeline.export.glb import glb_is_valid, write_glb


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
