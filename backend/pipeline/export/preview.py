from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def write_preview(output_dir: Path, xyz: np.ndarray, rgb: np.ndarray, frames: list[np.ndarray]) -> Path:
    path = output_dir / "preview.jpg"
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    canvas[:] = (18, 20, 24)

    if frames:
        thumb = frames[min(len(frames) // 2, len(frames) - 1)]
        if isinstance(thumb, (str, Path)):
            thumb = cv2.imread(str(thumb), cv2.IMREAD_COLOR)
        if thumb is not None and getattr(thumb, "size", 0):
            th = cv2.resize(thumb, (560, 360))
            canvas[40:400, 40:600] = th

    scatter = np.zeros((560, 560, 3), dtype=np.uint8)
    scatter[:] = (12, 14, 18)
    if len(xyz) > 0:
        xy = xyz[:, :2]
        mins = xy.min(axis=0)
        maxs = xy.max(axis=0)
        span = np.maximum(maxs - mins, 1e-6)
        norm = (xy - mins) / span
        px = (norm[:, 0] * 530 + 15).astype(int)
        py = ((1.0 - norm[:, 1]) * 530 + 15).astype(int)
        for x, y, color in zip(px, py, rgb):
            if 0 <= x < 560 and 0 <= y < 560:
                scatter[y, x] = (int(color[2]), int(color[1]), int(color[0]))
    canvas[80:640, 680:1240] = scatter
    cv2.putText(canvas, "Source frame", (40, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 220, 180), 1, cv2.LINE_AA)
    cv2.putText(canvas, "Top-down reconstruction", (680, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 220, 180), 1, cv2.LINE_AA)
    cv2.imwrite(str(path), canvas)
    return path
