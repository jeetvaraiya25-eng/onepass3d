from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from backend.pipeline.reconstruct.diagnostics import keep_largest_run, trajectory_is_connected
from backend.pipeline.reconstruct.poses import PoseGraph, camera_matrix


CAMERA_FAIL = "Reconstruction failed because insufficient overlapping views were available."


@dataclass
class SfmStats:
    frames: int = 0
    registered: int = 0
    matches: list[int] = field(default_factory=list)
    inliers: list[int] = field(default_factory=list)
    median_reproj: float = 99.0
    sparse_points: int = 0


@dataclass
class SfmResult:
    pose: PoseGraph
    registered: np.ndarray
    xyz: np.ndarray
    rgb: np.ndarray
    conf: np.ndarray
    stats: SfmStats


def _sift():
    return cv2.SIFT_create(nfeatures=3500, contrastThreshold=0.04, edgeThreshold=10)


def _match(desc_a, desc_b) -> list[cv2.DMatch]:
    if desc_a is None or desc_b is None or len(desc_a) < 12 or len(desc_b) < 12:
        return []
    index_params = dict(algorithm=1, trees=4)
    search = dict(checks=48)
    flann = cv2.FlannBasedMatcher(index_params, search)
    try:
        knn = flann.knnMatch(np.float32(desc_a), np.float32(desc_b), k=2)
    except cv2.error:
        return []
    good: list[cv2.DMatch] = []
    for pair in knn:
        if len(pair) < 2:
            continue
        a, b = pair
        if a.distance < 0.72 * b.distance:
            good.append(a)
    good.sort(key=lambda m: m.distance)
    return good[:2500]


def incremental_sfm(frames: list[np.ndarray]) -> SfmResult:
    """Sequential SIFT SfM. New cameras are registered by PnP against a shared map."""
    if len(frames) < 5:
        raise RuntimeError(CAMERA_FAIL)
    h, w = frames[0].shape[:2]
    K = _choose_intrinsics(w, h, frames)
    sift = _sift()
    kps: list[list[cv2.KeyPoint]] = []
    desc: list[np.ndarray | None] = []
    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        kp, de = sift.detectAndCompute(gray, None)
        kps.append(kp or [])
        desc.append(de)

    n = len(frames)
    rotations = [None] * n
    translations = [None] * n
    registered = np.zeros(n, dtype=bool)
    stats = SfmStats(frames=n)

    # 3D map: list of points, and (frame, kp_idx) -> point_id
    points: list[np.ndarray] = []
    colors: list[np.ndarray] = []
    obs: dict[tuple[int, int], int] = {}

    seed = _choose_seed(kps, desc, K)
    if seed is None:
        raise RuntimeError(CAMERA_FAIL)
    i0, i1, pts0, pts1, R, t, inl, matches = seed
    stats.matches.append(len(matches))
    stats.inliers.append(int(inl.sum()))

    rotations[i0] = np.eye(3, dtype=np.float64)
    translations[i0] = np.zeros(3, dtype=np.float64)
    rotations[i1] = R
    translations[i1] = t
    registered[i0] = registered[i1] = True

    xyz = _triangulate(pts0[inl], pts1[inl], K, rotations[i0], translations[i0], rotations[i1], translations[i1])
    rgb = _colors(frames[i0], pts0[inl][: len(xyz)])
    for p, c, m in zip(xyz, rgb, [matches[k] for k in np.where(inl)[0][: len(xyz)]]):
        if not np.isfinite(p).all():
            continue
        pid = len(points)
        points.append(p)
        colors.append(c)
        obs[(i0, m.queryIdx)] = pid
        obs[(i1, m.trainIdx)] = pid

    if len(points) < 40:
        raise RuntimeError(CAMERA_FAIL)

    for idx in range(i1 + 1, n):
        if desc[idx] is None:
            continue
        ok = _register_frame(idx, frames, kps, desc, K, rotations, translations, registered, points, colors, obs)
        if ok:
            stats.matches.append(ok[0])
            stats.inliers.append(ok[1])
    for idx in range(i0 - 1, -1, -1):
        if desc[idx] is None:
            continue
        ok = _register_frame(idx, frames, kps, desc, K, rotations, translations, registered, points, colors, obs)
        if ok:
            stats.matches.append(ok[0])
            stats.inliers.append(ok[1])

    registered = keep_largest_run(registered)
    reproj = _reprojection_errors(K, rotations, translations, points, obs, kps)
    stats.median_reproj = float(np.median(reproj)) if len(reproj) else 99.0
    stats.registered = int(registered.sum())
    stats.sparse_points = len(points)
    ok_traj, why, diag = trajectory_is_connected(registered)
    if not ok_traj or stats.median_reproj > 8.0 or len(points) < 80:
        raise RuntimeError(
            f"{CAMERA_FAIL} "
            f"(registered {stats.registered}/{n}, runs={diag.get('runs')}, "
            f"reproj={stats.median_reproj:.2f}px)"
        )

    pose = _pose_graph(K, rotations, translations, registered)
    xyz_a = np.asarray(points, dtype=np.float64)
    rgb_a = np.asarray(colors, dtype=np.uint8)
    conf = np.full(len(xyz_a), 0.88, dtype=np.float32)
    return SfmResult(pose=pose, registered=registered, xyz=xyz_a, rgb=rgb_a, conf=conf, stats=stats)


def _choose_seed(kps, desc, K):
    best = None
    best_score = -1
    n = len(kps)
    for i in range(min(n - 1, 12)):
        for j in (i + 1, i + 2):
            if j >= n:
                continue
            matches = _match(desc[i], desc[j])
            if len(matches) < 40:
                continue
            pts_a = np.float32([kps[i][m.queryIdx].pt for m in matches])
            pts_b = np.float32([kps[j][m.trainIdx].pt for m in matches])
            E, mask = cv2.findEssentialMat(pts_a, pts_b, K, cv2.RANSAC, 0.999, 1.0)
            if E is None or mask is None:
                continue
            inl = mask.ravel().astype(bool)
            if inl.sum() < 30:
                continue
            _, R, t, pmask = cv2.recoverPose(E, pts_a, pts_b, K, mask=mask)
            pmask = pmask.ravel().astype(bool)
            if pmask.sum() < 25:
                continue
            xyz = _triangulate(pts_a[pmask], pts_b[pmask], K, np.eye(3), np.zeros(3), R, t.reshape(3))
            if len(xyz) < 25:
                continue
            # Prefer a pair with baseline and a compact scene (not a wall of far noise).
            depth = xyz[:, 2] if np.allclose(R, np.eye(3), atol=0.2) else np.linalg.norm(xyz, axis=1)
            if float(np.median(np.abs(depth))) < 1e-3:
                continue
            score = int(pmask.sum()) + min(len(xyz), 400)
            if score > best_score:
                best_score = score
                best = (i, j, pts_a, pts_b, R, t.reshape(3), pmask, matches)
    return best


def _register_frame(idx, frames, kps, desc, K, rotations, translations, registered, points, colors, obs):
    # Match against the nearest already-registered frames.
    # Sequential only: previous (or next) registered frames in a short window.
    # Never PnP against a far-away island — that splits the reconstruction.
    if idx > 0:
        window = [i for i in range(idx - 1, max(-1, idx - 8), -1) if registered[i]]
    else:
        window = []
    if idx + 1 < len(registered):
        window += [i for i in range(idx + 1, min(len(registered), idx + 8)) if registered[i]]
    neighbors = window
    if not neighbors:
        return None
    pts3, pts2, src_matches = [], [], []
    match_count = 0
    for src in neighbors:
        matches = _match(desc[src], desc[idx])
        match_count += len(matches)
        for m in matches:
            key = (src, m.queryIdx)
            if key not in obs:
                continue
            pid = obs[key]
            pts3.append(points[pid])
            pts2.append(kps[idx][m.trainIdx].pt)
            src_matches.append((src, m, pid))
    if len(pts3) < 18:
        return None
    pts3 = np.asarray(pts3, dtype=np.float64)
    pts2 = np.asarray(pts2, dtype=np.float64)
    ok, rvec, tvec, inl = cv2.solvePnPRansac(
        pts3.reshape(-1, 1, 3),
        pts2.reshape(-1, 1, 2),
        K,
        None,
        flags=cv2.SOLVEPNP_EPNP,
        reprojectionError=3.0,
        iterationsCount=200,
        confidence=0.99,
    )
    if not ok or inl is None or len(inl) < 16:
        return None
    rvec, tvec = cv2.solvePnPRefineLM(pts3[inl.ravel()], pts2[inl.ravel()], K, None, rvec, tvec)[:2]
    R, _ = cv2.Rodrigues(rvec)
    t = tvec.reshape(3)
    rotations[idx] = R
    translations[idx] = t
    registered[idx] = True

    for src, m, pid in src_matches:
        obs[(idx, m.trainIdx)] = pid

    # Triangulate new tracks against the closest registered neighbor.
    src = min(neighbors, key=lambda i: abs(i - idx))
    matches = _match(desc[src], desc[idx])
    new_a, new_b, new_m = [], [], []
    for m in matches:
        if (src, m.queryIdx) in obs or (idx, m.trainIdx) in obs:
            continue
        new_a.append(kps[src][m.queryIdx].pt)
        new_b.append(kps[idx][m.trainIdx].pt)
        new_m.append(m)
    if len(new_a) >= 12:
        pa, pb = np.float32(new_a), np.float32(new_b)
        xyz = _triangulate(pa, pb, K, rotations[src], translations[src], rotations[idx], translations[idx])
        rgb = _colors(frames[src], pa[: len(xyz)])
        for p, c, m in zip(xyz, rgb, new_m[: len(xyz)]):
            if not np.isfinite(p).all():
                continue
            if _reproj(K, rotations[idx], translations[idx], p, kps[idx][m.trainIdx].pt) > 2.8:
                continue
            pid = len(points)
            points.append(p)
            colors.append(c)
            obs[(src, m.queryIdx)] = pid
            obs[(idx, m.trainIdx)] = pid
    return match_count, int(len(inl))


def _triangulate(pts_a, pts_b, K, Ra, ta, Rb, tb) -> np.ndarray:
    if len(pts_a) == 0:
        return np.zeros((0, 3), dtype=np.float64)
    P1 = K @ np.hstack([Ra, ta.reshape(3, 1)])
    P2 = K @ np.hstack([Rb, tb.reshape(3, 1)])
    homog = cv2.triangulatePoints(P1, P2, np.asarray(pts_a, np.float64).T, np.asarray(pts_b, np.float64).T)
    w = homog[3]
    valid = np.abs(w) > 1e-8
    xyz = np.zeros((homog.shape[1], 3), dtype=np.float64)
    xyz[valid] = (homog[:3, valid] / w[valid]).T
    cam_a = Ra @ xyz.T + ta.reshape(3, 1)
    cam_b = Rb @ xyz.T + tb.reshape(3, 1)
    # Parallax: reject points seen at a tiny angle (unstable depth).
    va = xyz - (-Ra.T @ ta)
    vb = xyz - (-Rb.T @ tb)
    va /= np.clip(np.linalg.norm(va, axis=1, keepdims=True), 1e-8, None)
    vb /= np.clip(np.linalg.norm(vb, axis=1, keepdims=True), 1e-8, None)
    angle = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", va, vb), -1, 1)))
    keep = (
        valid
        & (cam_a[2] > 0.05)
        & (cam_b[2] > 0.05)
        & (cam_a[2] < 80.0)
        & (cam_b[2] < 80.0)
        & (angle > 1.2)
        & np.isfinite(xyz).all(axis=1)
    )
    return xyz[keep]


def _reproj(K, R, t, xyz, uv) -> float:
    cam = R @ xyz.reshape(3) + t
    if cam[2] <= 1e-6:
        return 999.0
    pix = K @ cam
    u, v = pix[0] / pix[2], pix[1] / pix[2]
    return float(np.hypot(u - uv[0], v - uv[1]))


def _reprojection_errors(K, rotations, translations, points, obs, kps) -> np.ndarray:
    err = []
    for (fi, ki), pid in obs.items():
        if rotations[fi] is None or pid >= len(points):
            continue
        uv = kps[fi][ki].pt
        err.append(_reproj(K, rotations[fi], translations[fi], points[pid], uv))
    return np.asarray(err, dtype=np.float64) if err else np.zeros(0)


def _colors(frame, pts):
    h, w = frame.shape[:2]
    if len(pts) == 0:
        return np.zeros((0, 3), dtype=np.uint8)
    xi = np.clip(np.asarray(pts)[:, 0].astype(np.int32), 0, w - 1)
    yi = np.clip(np.asarray(pts)[:, 1].astype(np.int32), 0, h - 1)
    return frame[yi, xi][:, ::-1].copy()


def _refine_poses(K, rotations, translations, registered, points, obs, kps) -> None:
    by_cam: dict[int, list] = {}
    for (fi, ki), pid in obs.items():
        if not registered[fi] or pid >= len(points) or rotations[fi] is None:
            continue
        by_cam.setdefault(fi, []).append((points[pid], kps[fi][ki].pt))
    for fi, pairs in by_cam.items():
        if len(pairs) < 12:
            continue
        xyz = np.asarray([p[0] for p in pairs], dtype=np.float64)
        uv = np.asarray([p[1] for p in pairs], dtype=np.float64)
        rvec, _ = cv2.Rodrigues(rotations[fi])
        tvec = translations[fi].reshape(3, 1)
        try:
            rvec, tvec = cv2.solvePnPRefineLM(xyz, uv, K, None, rvec, tvec)
        except cv2.error:
            continue
        rotations[fi], _ = cv2.Rodrigues(rvec)
        translations[fi] = tvec.reshape(3)


def _choose_intrinsics(w: int, h: int, frames: list[np.ndarray]) -> np.ndarray:
    """Pick a pinhole FOV that explains the first overlapping pair. Distortion starts at zero."""
    sift = _sift()
    gray0 = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
    gray1 = cv2.cvtColor(frames[min(1, len(frames) - 1)], cv2.COLOR_BGR2GRAY)
    kp0, d0 = sift.detectAndCompute(gray0, None)
    kp1, d1 = sift.detectAndCompute(gray1, None)
    matches = _match(d0, d1)
    if len(matches) < 30:
        return camera_matrix(w, h, fov_deg=68.0)
    pts_a = np.float32([kp0[m.queryIdx].pt for m in matches])
    pts_b = np.float32([kp1[m.trainIdx].pt for m in matches])
    best_k, best_n = camera_matrix(w, h, 68.0), -1
    for fov in (52.0, 60.0, 68.0, 76.0, 84.0):
        K = camera_matrix(w, h, fov)
        E, mask = cv2.findEssentialMat(pts_a, pts_b, K, cv2.RANSAC, 0.999, 1.0)
        ninl = int(mask.ravel().sum()) if mask is not None else 0
        if ninl > best_n:
            best_n, best_k = ninl, K
    return best_k


def _pose_graph(K, rotations, translations, registered) -> PoseGraph:
    n = len(rotations)
    Rs, ts, centers = [], [], []
    for i in range(n):
        if registered[i] and rotations[i] is not None:
            R, t = rotations[i], translations[i]
        else:
            R, t = np.eye(3), np.zeros(3)
        Rs.append(R.copy())
        ts.append(t.copy())
        centers.append((-R.T @ t).reshape(3))
    return PoseGraph(K=K, rotations=Rs, translations=ts, centers=np.asarray(centers))


def assess_poses(result: SfmResult) -> dict:
    stats = result.stats
    ok, _why, diag = trajectory_is_connected(result.registered)
    if not ok:
        raise RuntimeError(CAMERA_FAIL)
    if stats.median_reproj > 8.0:
        raise RuntimeError(CAMERA_FAIL)
    steps = np.linalg.norm(np.diff(result.pose.centers[result.registered], axis=0), axis=1)
    if len(steps) and float(np.median(steps)) < 1e-5:
        raise RuntimeError(CAMERA_FAIL)
    return {
        "registered": stats.registered,
        "frames": stats.frames,
        "median_reproj": stats.median_reproj,
        "sparse_points": stats.sparse_points,
        "mean_inliers": float(np.mean(stats.inliers)) if stats.inliers else 0.0,
        "mean_matches": float(np.mean(stats.matches)) if stats.matches else 0.0,
        "registered_indices": diag["registered_indices"],
        "runs": diag["runs"],
        "longest_run": diag.get("longest_run"),
        "fx": float(result.pose.K[0, 0]),
        "fy": float(result.pose.K[1, 1]),
        "cx": float(result.pose.K[0, 2]),
        "cy": float(result.pose.K[1, 2]),
        "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
    }
