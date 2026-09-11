import pytest

from backend.pipeline.reconstruct.colmap.service import ColmapMissing, ColmapService
from backend.pipeline.reconstruct.colmap.workspace import ColmapWorkspace


def test_service_requires_colmap(tmp_path):
    ws = ColmapWorkspace(tmp_path)
    ws.create()
    with pytest.raises(ColmapMissing):
        ColmapService(ws, info={"installed": False, "path": "", "device": "cpu"})
