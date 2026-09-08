from __future__ import annotations

import numpy as np

from backend.pipeline.geo.crs import apply_sim3, interpolate_trajectory, telemetry_to_enu, trajectory_length, umeyama


def align_to_gps(
    camera_centers: np.ndarray,
    telemetry: list[dict[str, float]],
) -> tuple[np.ndarray, dict]:
    """Scale and rigid-align VO camera centers to GPS ENU. Returns aligned centers + meta."""
    enu, origin = telemetry_to_enu(telemetry)
    gps_path = interpolate_trajectory(enu, len(camera_centers))
    vo_len = trajectory_length(camera_centers)
    gps_len = trajectory_length(gps_path)
    meta = {
        "origin": origin,
        "gps_points": len(telemetry),
        "gps_path_m": gps_len,
        "vo_path": vo_len,
        "metric": False,
        "scale": 1.0,
    }
    if len(camera_centers) < 2 or gps_len < 1e-3:
        return camera_centers, meta

    if vo_len < 1e-8:
        aligned = gps_path.copy()
        meta.update({"metric": True, "scale": 1.0, "method": "gps_only"})
        return aligned, meta

    scale, rotation, translation = umeyama(camera_centers, gps_path, with_scale=True)
    aligned = apply_sim3(camera_centers, scale, rotation, translation)
    rms = float(np.sqrt(np.mean(np.sum((aligned - gps_path) ** 2, axis=1))))
    meta.update(
        {
            "metric": True,
            "scale": scale,
            "rotation": rotation.tolist(),
            "translation": translation.tolist(),
            "rms_m": rms,
            "method": "umeyama_gps",
        }
    )
    return aligned, meta


def transform_points(
    points: np.ndarray,
    camera_centers: np.ndarray,
    aligned_centers: np.ndarray,
) -> tuple[np.ndarray, dict]:
    if len(camera_centers) < 3 or len(points) == 0:
        return points, {"metric": False, "scale": 1.0}
    scale, rotation, translation = umeyama(camera_centers, aligned_centers, with_scale=True)
    return apply_sim3(points, scale, rotation, translation), {
        "metric": True,
        "scale": scale,
        "rotation": rotation.tolist(),
        "translation": translation.tolist(),
    }
