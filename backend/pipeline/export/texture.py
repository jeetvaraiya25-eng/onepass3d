from __future__ import annotations

import numpy as np

from backend.pipeline.reconstruct.poses import PoseGraph


def color_from_frames(
    xyz: np.ndarray,
    rgb: np.ndarray,
    frames: list[np.ndarray],
    pose: PoseGraph,
) -> np.ndarray:
    """Paint vertices from the original video frames (best visible camera)."""
    if len(xyz) == 0 or not frames or pose is None:
        return rgb
    out = rgb.astype(np.float64)
    best = np.full(len(xyz), -1.0, dtype=np.float64)
    K = pose.K
    for i, frame in enumerate(frames):
        if i >= len(pose.rotations):
            break
        h, w = frame.shape[:2]
        cam = pose.rotations[i] @ xyz.T + pose.translations[i].reshape(3, 1)
        z = cam[2]
        visible = z > 0.05
        if not visible.any():
            continue
        pix = K @ cam
        u = pix[0] / np.clip(pix[2], 1e-6, None)
        v = pix[1] / np.clip(pix[2], 1e-6, None)
        inside = visible & (u >= 1) & (v >= 1) & (u < w - 1) & (v < h - 1)
        if not inside.any():
            continue
        score = inside.astype(np.float64) / np.clip(z, 0.05, None)
        better = score > best
        if not better.any():
            continue
        ui = np.clip(u[better].astype(np.int32), 0, w - 1)
        vi = np.clip(v[better].astype(np.int32), 0, h - 1)
        bgr = frame[vi, ui]
        out[better] = bgr[:, ::-1]
        best[better] = score[better]
    return np.clip(out, 0, 255).astype(np.uint8)
