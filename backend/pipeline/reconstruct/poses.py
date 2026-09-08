from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class PoseGraph:
    K: np.ndarray
    rotations: list[np.ndarray]
    translations: list[np.ndarray]
    centers: np.ndarray


def camera_matrix(width: int, height: int, fov_deg: float = 72.0) -> np.ndarray:
    fov = np.deg2rad(fov_deg)
    fx = width / (2.0 * np.tan(fov / 2.0))
    fy = fx
    cx = width / 2.0
    cy = height / 2.0
    return np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)


def _orb() -> cv2.ORB:
    return cv2.ORB_create(nfeatures=6000, scaleFactor=1.2, nlevels=8)


def match_features(desc_a: np.ndarray, desc_b: np.ndarray) -> list[cv2.DMatch]:
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    knn = matcher.knnMatch(desc_a, desc_b, k=2)
    good: list[cv2.DMatch] = []
    for pair in knn:
        if len(pair) < 2:
            continue
        best, rest = pair
        if best.distance < 0.75 * rest.distance:
            good.append(best)
    good.sort(key=lambda m: m.distance)
    return good[:1500]


def relative_pose(
    pts_a: np.ndarray,
    pts_b: np.ndarray,
    K: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    if len(pts_a) < 12:
        return None
    essential, mask = cv2.findEssentialMat(
        pts_a,
        pts_b,
        K,
        method=cv2.RANSAC,
        prob=0.999,
        threshold=1.2,
    )
    if essential is not None:
        mask_e = mask.ravel().astype(bool)
        if mask_e.sum() >= 10:
            _, R, t, pose_mask = cv2.recoverPose(
                essential, pts_a, pts_b, K, mask=mask_e.astype(np.uint8)[:, None]
            )
            inliers = pose_mask.ravel().astype(bool)
            if inliers.sum() >= 8:
                return R, t.reshape(3), inliers
    return pose_from_homography(pts_a, pts_b, K)


def pose_from_homography(
    pts_a: np.ndarray,
    pts_b: np.ndarray,
    K: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Planar / nadir fallback when the essential matrix is degenerate."""
    H, mask = cv2.findHomography(pts_a, pts_b, cv2.RANSAC, 2.5)
    if H is None:
        return None
    inliers = mask.ravel().astype(bool) if mask is not None else np.ones(len(pts_a), dtype=bool)
    if inliers.sum() < 8:
        return None
    try:
        nsol, Rs, Ts, Ns = cv2.decomposeHomographyMat(H, K)
    except cv2.error:
        return None
    best = None
    best_score = -1
    for i in range(nsol):
        R = Rs[i]
        t = Ts[i].reshape(3)
        if np.linalg.norm(t) < 1e-8:
            continue
        t = t / (np.linalg.norm(t) + 1e-8)
        # Count points with positive depth in both cameras.
        pts = cv2.convertPointsToHomogeneous(pts_a[inliers]).reshape(-1, 3).T
        x1 = np.linalg.inv(K) @ pts
        x1 = x1 / np.clip(x1[2], 1e-8, None)
        x2 = R @ x1 + t.reshape(3, 1)
        score = int(((x1[2] > 0) & (x2[2] > 0)).sum())
        if score > best_score:
            best_score = score
            best = (R, t, inliers)
    return best


def estimate_poses(frames: list[np.ndarray]) -> tuple[PoseGraph, list[dict]]:
    if not frames:
        raise RuntimeError("No frames for pose estimation.")
    h, w = frames[0].shape[:2]
    K = camera_matrix(w, h)
    orb = _orb()

    keypoints: list[list[cv2.KeyPoint]] = []
    descriptors: list[np.ndarray] = []
    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        kps, desc = orb.detectAndCompute(gray, None)
        if desc is None or len(kps) < 20:
            keypoints.append([])
            descriptors.append(np.zeros((0, 32), dtype=np.uint8))
        else:
            keypoints.append(kps)
            descriptors.append(desc)

    rotations = [np.eye(3, dtype=np.float64)]
    translations = [np.zeros(3, dtype=np.float64)]
    pair_data: list[dict] = []

    for i in range(1, len(frames)):
        prev = i - 1
        R = np.eye(3)
        t = np.array([0.04, 0.0, 0.0], dtype=np.float64)
        inliers = np.zeros(0, dtype=bool)
        pts_a = pts_b = np.zeros((0, 2), dtype=np.float64)
        matches: list[cv2.DMatch] = []

        if len(descriptors[prev]) and len(descriptors[i]):
            matches = match_features(descriptors[prev], descriptors[i])
            if len(matches) >= 12:
                pts_a = np.float32([keypoints[prev][m.queryIdx].pt for m in matches])
                pts_b = np.float32([keypoints[i][m.trainIdx].pt for m in matches])
                recovered = relative_pose(pts_a, pts_b, K)
                if recovered is not None:
                    R, t, inliers = recovered

        rotations.append(R @ rotations[-1])
        translations.append(translations[-1] + rotations[-1] @ t)
        pair_data.append(
            {
                "i": prev,
                "j": i,
                "pts_a": pts_a,
                "pts_b": pts_b,
                "inliers": inliers,
                "matches": matches,
                "kps_a": keypoints[prev],
                "kps_b": keypoints[i],
            }
        )

    centers = []
    for R, t in zip(rotations, translations):
        centers.append((-R.T @ t).reshape(3))
    graph = PoseGraph(K=K, rotations=rotations, translations=translations, centers=np.asarray(centers))
    return graph, pair_data
