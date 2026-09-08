from __future__ import annotations

import cv2
import numpy as np

from backend.pipeline.reconstruct.poses import PoseGraph


def _triangulate_pair(
    pts_a: np.ndarray,
    pts_b: np.ndarray,
    pose: PoseGraph,
    i: int,
    j: int,
) -> np.ndarray:
    if len(pts_a) == 0:
        return np.zeros((0, 3), dtype=np.float64)
    P1 = pose.K @ np.hstack([pose.rotations[i], pose.translations[i].reshape(3, 1)])
    P2 = pose.K @ np.hstack([pose.rotations[j], pose.translations[j].reshape(3, 1)])
    homog = cv2.triangulatePoints(P1, P2, pts_a.T, pts_b.T)
    w = homog[3]
    valid = np.abs(w) > 1e-8
    xyz = np.zeros((homog.shape[1], 3), dtype=np.float64)
    xyz[valid] = (homog[:3, valid] / w[valid]).T
    cam = pose.rotations[i] @ xyz.T + pose.translations[i].reshape(3, 1)
    depth = cam[2]
    keep = valid & (depth > 0.02) & (depth < 250.0) & np.isfinite(xyz).all(axis=1)
    return xyz[keep]


def triangulate_sparse(pose: PoseGraph, pair_data: list[dict], frames: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points: list[np.ndarray] = []
    colors: list[np.ndarray] = []
    confidence: list[np.ndarray] = []

    for pair in pair_data:
        pts_a = pair["pts_a"]
        pts_b = pair["pts_b"]
        inliers = pair["inliers"]
        if len(pts_a) == 0:
            continue
        if inliers is not None and len(inliers) == len(pts_a):
            pts_a = pts_a[inliers]
            pts_b = pts_b[inliers]
        xyz = _triangulate_pair(pts_a, pts_b, pose, pair["i"], pair["j"])
        if len(xyz) == 0:
            continue
        frame = frames[pair["i"]]
        sample = pts_a[: len(xyz)]
        rgb = _sample_colors(frame, sample[: len(xyz)])
        n = min(len(xyz), len(rgb))
        points.append(xyz[:n])
        colors.append(rgb[:n])
        conf = np.full(n, 0.82, dtype=np.float32)
        confidence.append(conf)

    return _stack(points, colors, confidence)


def triangulate_semidense(
    frames: list[np.ndarray],
    pose: PoseGraph,
    motion_masks: list[np.ndarray] | None = None,
    grid: int = 96,
    spans: tuple[int, ...] = (1, 2),
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points: list[np.ndarray] = []
    colors: list[np.ndarray] = []
    confidence: list[np.ndarray] = []
    lk = dict(winSize=(31, 31), maxLevel=4, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 25, 0.03))

    for span in spans:
        for i in range(len(frames) - span):
            j = i + span
            gray_a = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            gray_b = cv2.cvtColor(frames[j], cv2.COLOR_BGR2GRAY)
            if gray_a.shape != gray_b.shape:
                gray_b = cv2.resize(gray_b, (gray_a.shape[1], gray_a.shape[0]), interpolation=cv2.INTER_AREA)
            h, w = gray_a.shape
            ys, xs = np.meshgrid(
                np.linspace(10, h - 10, grid),
                np.linspace(10, w - 10, grid),
                indexing="ij",
            )
            pts = np.column_stack([xs.ravel(), ys.ravel()]).astype(np.float32)
            if motion_masks is not None and i < len(motion_masks):
                mask = motion_masks[i]
                xi = np.clip(pts[:, 0].astype(np.int32), 0, mask.shape[1] - 1)
                yi = np.clip(pts[:, 1].astype(np.int32), 0, mask.shape[0] - 1)
                pts = pts[mask[yi, xi] == 0]
            if len(pts) < 20:
                continue
            try:
                tracked, status, err = cv2.calcOpticalFlowPyrLK(gray_a, gray_b, pts, None, **lk)
            except cv2.error:
                continue
            if tracked is None or status is None or err is None:
                continue
            status = status.reshape(-1).astype(bool)
            err = err.reshape(-1)
            good = status & (err < 20.0)
            pts_a = pts[good]
            pts_b = tracked[good]
            flow = np.linalg.norm(pts_b - pts_a, axis=1)
            keep = (flow > 0.6) & (flow < 160.0)
            pts_a, pts_b = pts_a[keep], pts_b[keep]
            xyz = _triangulate_pair(pts_a, pts_b, pose, i, j)
            if len(xyz) == 0:
                continue
            n = min(len(xyz), len(pts_a))
            rgb = _sample_colors(frames[i], pts_a[:n])
            conf = np.clip(1.0 - (err[good][keep][:n] / 14.0), 0.25, 0.98).astype(np.float32)
            points.append(xyz[:n])
            colors.append(rgb[:n])
            confidence.append(conf[:n])

    return _stack(points, colors, confidence)


def _sample_colors(frame: np.ndarray, pts: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    if len(pts) == 0:
        return np.zeros((0, 3), dtype=np.uint8)
    xi = np.clip(pts[:, 0].astype(np.int32), 0, w - 1)
    yi = np.clip(pts[:, 1].astype(np.int32), 0, h - 1)
    bgr = frame[yi, xi]
    return bgr[:, ::-1].copy()


def _stack(
    points: list[np.ndarray],
    colors: list[np.ndarray],
    confidence: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not points:
        return (
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0, 3), dtype=np.uint8),
            np.zeros((0,), dtype=np.float32),
        )
    xyz = np.concatenate(points, axis=0)
    rgb = np.concatenate(colors, axis=0)
    conf = np.concatenate(confidence, axis=0)
    finite = np.isfinite(xyz).all(axis=1)
    return xyz[finite], rgb[finite], conf[finite]


def filter_outliers(
    xyz: np.ndarray,
    rgb: np.ndarray,
    conf: np.ndarray,
    keep_percentile: float = 93.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(xyz) < 40:
        return xyz, rgb, conf
    med = np.median(xyz, axis=0)
    dist = np.linalg.norm(xyz - med, axis=1)
    limit = float(np.percentile(dist, keep_percentile))
    keep = dist <= max(limit, 1e-6)
    return xyz[keep], rgb[keep], conf[keep]


def downsample_points(
    xyz: np.ndarray,
    rgb: np.ndarray,
    conf: np.ndarray,
    voxel: float | None = None,
    max_points: int = 400_000,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(xyz) == 0:
        return xyz, rgb, conf
    if voxel is None:
        extent = np.ptp(xyz, axis=0).max()
        voxel = max(extent / 320.0, 1e-4)
    keys = np.floor(xyz / voxel).astype(np.int32)
    _, indices = np.unique(keys, axis=0, return_index=True)
    xyz, rgb, conf = xyz[indices], rgb[indices], conf[indices]
    if len(xyz) > max_points:
        pick = np.random.default_rng(0).choice(len(xyz), size=max_points, replace=False)
        xyz, rgb, conf = xyz[pick], rgb[pick], conf[pick]
    return xyz, rgb, conf
