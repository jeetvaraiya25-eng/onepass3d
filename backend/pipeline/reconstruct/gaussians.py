from __future__ import annotations

import numpy as np


SH_C0 = 0.28209479177387814


def inverse_sigmoid(x: float) -> float:
    x = min(max(x, 1e-4), 1 - 1e-4)
    return float(np.log(x / (1.0 - x)))


def points_to_gaussians(xyz: np.ndarray, rgb: np.ndarray) -> dict[str, np.ndarray]:
    """Pack a 3DGS-style Gaussian cloud from a colored point cloud."""
    n = len(xyz)
    if n == 0:
        return {
            "xyz": xyz,
            "f_dc": np.zeros((0, 3), dtype=np.float32),
            "opacity": np.zeros((0,), dtype=np.float32),
            "scale": np.zeros((0, 3), dtype=np.float32),
            "rot": np.zeros((0, 4), dtype=np.float32),
        }

    extent = float(np.ptp(xyz, axis=0).max())
    radius = float(max(extent / max((n ** (1.0 / 3.0)) * 4.2, 1.0), 1e-4))

    color = rgb.astype(np.float64) / 255.0
    f_dc = ((color - 0.5) / SH_C0).astype(np.float32)
    opacity = np.full(n, inverse_sigmoid(0.86), dtype=np.float32)
    scale = np.full((n, 3), np.log(radius), dtype=np.float32)
    rot = np.zeros((n, 4), dtype=np.float32)
    rot[:, 0] = 1.0
    return {"xyz": xyz.astype(np.float32), "f_dc": f_dc, "opacity": opacity, "scale": scale, "rot": rot}
