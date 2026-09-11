from __future__ import annotations

from backend.pipeline.reconstruct.colmap.detector import check_colmap_installation


def colmap_bin() -> str | None:
    info = check_colmap_installation()
    return info["path"] if info.get("installed") else None
