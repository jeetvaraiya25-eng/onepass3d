from __future__ import annotations

import cv2
import numpy as np

from backend.pipeline.reconstruct.poses import PoseGraph


def dense_multiview(
    frames: list[np.ndarray],
    pose: PoseGraph,
    registered: np.ndarray | None = None,
    spans: tuple[int, ...] = (1, 2),
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fuse stereo depth from overlapping registered views. Requires consistent SfM poses."""
    n = len(frames)
    if registered is None:
        registered = np.ones(n, dtype=bool)
    points, colors, confs = [], [], []
    pairs = []
    for span in spans:
        for i in range(n - span):
            j = i + span
            if registered[i] and registered[j]:
                pairs.append((i, j))
    if len(pairs) > 40:
        step = max(1, len(pairs) // 40)
        pairs = pairs[::step]
    for i, j in pairs:
        xyz, rgb, conf = _stereo_pair(frames[i], frames[j], pose, i, j)
        if len(xyz) == 0:
            continue
        keep = _third_view_ok(xyz, pose, i, registered, n)
        xyz, rgb, conf = xyz[keep], rgb[keep], conf[keep]
        if len(xyz):
            points.append(xyz)
            colors.append(rgb)
            confs.append(conf)
    if not points:
        return (
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0, 3), dtype=np.uint8),
            np.zeros((0,), dtype=np.float32),
        )
    return np.concatenate(points), np.concatenate(colors), np.concatenate(confs)


def _relative(pose: PoseGraph, i: int, j: int):
    Ri, ti = pose.rotations[i], pose.translations[i]
    Rj, tj = pose.rotations[j], pose.translations[j]
    R = Rj @ Ri.T
    t = tj - R @ ti
    return R, t


def _stereo_pair(img_a, img_b, pose: PoseGraph, i: int, j: int):
    h, w = img_a.shape[:2]
    if img_b.shape[:2] != (h, w):
        img_b = cv2.resize(img_b, (w, h), interpolation=cv2.INTER_AREA)
    K = pose.K.copy()
    long_edge = max(h, w)
    if long_edge > 720:
        scale = 720.0 / long_edge
        img_a = cv2.resize(img_a, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        img_b = cv2.resize(img_b, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        h, w = img_a.shape[:2]
        K[:2] *= scale
    R, t = _relative(pose, i, j)
    if np.linalg.norm(t) < 1e-6:
        return _empty()
    try:
        R1, R2, P1, P2, Q, _, _ = cv2.stereoRectify(
            K, None, K, None, (w, h), R, t, flags=cv2.CALIB_ZERO_DISPARITY, alpha=0
        )
        m1x, m1y = cv2.initUndistortRectifyMap(K, None, R1, P1, (w, h), cv2.CV_32FC1)
        m2x, m2y = cv2.initUndistortRectifyMap(K, None, R2, P2, (w, h), cv2.CV_32FC1)
    except cv2.error:
        return _empty()
    left = cv2.remap(img_a, m1x, m1y, cv2.INTER_LINEAR)
    right = cv2.remap(img_b, m2x, m2y, cv2.INTER_LINEAR)
    gray_l = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
    gray_r = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
    num = 16 * 8
    stereo = cv2.StereoSGBM_create(
        minDisparity=0,
        numDisparities=num,
        blockSize=5,
        P1=8 * 3 * 25,
        P2=32 * 3 * 25,
        uniquenessRatio=12,
        speckleWindowSize=80,
        speckleRange=2,
        disp12MaxDiff=2,
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
    )
    disp = stereo.compute(gray_l, gray_r).astype(np.float32) / 16.0
    valid = disp > 1.0
    if valid.sum() < 200:
        return _empty()
    # Subsample the disparity map — full pixels are too many and too noisy.
    step = 3
    ys, xs = np.where(valid)
    pick = np.arange(0, len(xs), step)
    xs, ys = xs[pick], ys[pick]
    disp_v = disp[ys, xs]
    pts = cv2.convertPointsToHomogeneous(np.column_stack([xs, ys, disp_v])).reshape(-1, 4)
    cam = (Q @ pts.T).T
    w = cam[:, 3]
    keep_w = np.abs(w) > 1e-8
    xyz_rect = np.zeros((len(cam), 3), dtype=np.float64)
    xyz_rect[keep_w] = cam[keep_w, :3] / w[keep_w, None]
    # Rectified cam i -> original cam i -> world
    xyz_cam = (R1.T @ xyz_rect.T).T
    depth = xyz_cam[:, 2]
    keep = keep_w & (depth > 0.08) & (depth < 25.0) & np.isfinite(xyz_cam).all(axis=1)
    xyz_cam = xyz_cam[keep]
    xs, ys = xs[keep], ys[keep]
    if len(xyz_cam) == 0:
        return _empty()
    Ri, ti = pose.rotations[i], pose.translations[i]
    xyz = (Ri.T @ (xyz_cam.T - ti.reshape(3, 1))).T
    bgr = left[ys, xs]
    rgb = bgr[:, ::-1].copy()
    conf = np.clip(0.35 + 0.5 * (disp_v[keep] / (disp_v[keep].max() + 1e-6)), 0.3, 0.95).astype(np.float32)
    return xyz, rgb, conf


def _third_view_ok(xyz, pose: PoseGraph, i: int, registered: np.ndarray, n: int) -> np.ndarray:
    k = None
    for cand in (i + 2, i + 3, i - 1, i + 1):
        if 0 <= cand < n and cand != i and registered[cand]:
            k = cand
            break
    if k is None:
        return np.ones(len(xyz), dtype=bool)
    R, t = pose.rotations[k], pose.translations[k]
    cam = R @ xyz.T + t.reshape(3, 1)
    z = cam[2]
    pix = pose.K @ cam
    u = pix[0] / np.clip(z, 1e-6, None)
    v = pix[1] / np.clip(z, 1e-6, None)
    # We don't have exact image size here; use principal point * 2 as a proxy.
    w = float(pose.K[0, 2] * 2)
    h = float(pose.K[1, 2] * 2)
    return (z > 0.08) & (z < 25.0) & (u >= 0) & (v >= 0) & (u < w) & (v < h)


def _empty():
    return (
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 3), dtype=np.uint8),
        np.zeros((0,), dtype=np.float32),
    )
