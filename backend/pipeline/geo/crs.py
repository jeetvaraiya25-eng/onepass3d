from __future__ import annotations

import math

import numpy as np


WGS84_A = 6378137.0
WGS84_E2 = 6.69437999014e-3


def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt: float) -> np.ndarray:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + alt) * cos_lat * cos_lon
    y = (n + alt) * cos_lat * sin_lon
    z = (n * (1.0 - WGS84_E2) + alt) * sin_lat
    return np.array([x, y, z], dtype=np.float64)


def ecef_to_enu_matrix(lat_deg: float, lon_deg: float) -> np.ndarray:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    return np.array(
        [
            [-sin_lon, cos_lon, 0.0],
            [-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat],
            [cos_lat * cos_lon, cos_lat * sin_lon, sin_lat],
        ],
        dtype=np.float64,
    )


def telemetry_to_enu(points: list[dict[str, float]]) -> tuple[np.ndarray, dict[str, float]]:
    origin = points[0]
    r0 = geodetic_to_ecef(origin["lat"], origin["lon"], origin["alt"])
    rot = ecef_to_enu_matrix(origin["lat"], origin["lon"])
    enu = []
    for point in points:
        r = geodetic_to_ecef(point["lat"], point["lon"], point["alt"])
        enu.append(rot @ (r - r0))
    return np.asarray(enu, dtype=np.float64), origin


def interpolate_trajectory(enu: np.ndarray, count: int) -> np.ndarray:
    if len(enu) == 0 or count <= 0:
        return np.zeros((0, 3), dtype=np.float64)
    if len(enu) == 1:
        return np.repeat(enu, count, axis=0)
    src = np.linspace(0.0, 1.0, len(enu))
    dst = np.linspace(0.0, 1.0, count)
    out = np.column_stack([np.interp(dst, src, enu[:, i]) for i in range(3)])
    return out


def umeyama(source: np.ndarray, target: np.ndarray, with_scale: bool = True) -> tuple[float, np.ndarray, np.ndarray]:
    """Return (scale, rotation, translation) mapping source -> target."""
    assert source.shape == target.shape
    n = source.shape[0]
    mu_s = source.mean(axis=0)
    mu_t = target.mean(axis=0)
    src = source - mu_s
    dst = target - mu_t
    cov = (dst.T @ src) / n
    u, s, vh = np.linalg.svd(cov)
    d = np.ones(3)
    if np.linalg.det(u) * np.linalg.det(vh) < 0:
        d[-1] = -1.0
    rot = u @ np.diag(d) @ vh
    var_s = (src ** 2).sum() / n
    scale = float((s * d).sum() / var_s) if with_scale and var_s > 1e-12 else 1.0
    translation = mu_t - scale * rot @ mu_s
    return scale, rot, translation


def apply_sim3(points: np.ndarray, scale: float, rotation: np.ndarray, translation: np.ndarray) -> np.ndarray:
    return (scale * (rotation @ points.T).T) + translation


def trajectory_length(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())
