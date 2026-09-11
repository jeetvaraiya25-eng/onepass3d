from __future__ import annotations

import cv2
import numpy as np

from backend.app.config import MIN_FRAMES, quality_preset


def sharpness(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def histogram_signature(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [24, 32], [0, 180, 0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    return hist


def is_duplicate(hist_a: np.ndarray, hist_b: np.ndarray, threshold: float = 0.97) -> bool:
    a = hist_a.astype(np.float64).ravel()
    b = hist_b.astype(np.float64).ravel()
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8
    return float(a @ b) / denom >= threshold


def exposure_ok(image: np.ndarray) -> bool:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mean = float(gray.mean())
    if mean < 18.0 or mean > 245.0:
        return False
    dark = float((gray < 12).mean())
    bright = float((gray > 250).mean())
    if dark > 0.82 or bright > 0.82:
        return False
    return True


def _motion(prev: np.ndarray, cur: np.ndarray) -> float:
    a = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)
    a = cv2.resize(a, (160, 90), interpolation=cv2.INTER_AREA)
    b = cv2.resize(b, (160, 90), interpolation=cv2.INTER_AREA)
    flow = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    return float(np.median(np.linalg.norm(flow, axis=2)))


def _orb_matches(prev: np.ndarray, cur: np.ndarray) -> int:
    orb = cv2.ORB_create(nfeatures=1200)
    g0 = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    g1 = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)
    k0, d0 = orb.detectAndCompute(g0, None)
    k1, d1 = orb.detectAndCompute(g1, None)
    if d0 is None or d1 is None or len(k0) < 20 or len(k1) < 20:
        return 0
    knn = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(d0, d1, k=2)
    good = 0
    for pair in knn:
        if len(pair) < 2:
            continue
        a, b = pair
        if a.distance < 0.78 * b.distance:
            good += 1
    return good


def _feature_count(image: np.ndarray) -> int:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=1500)
    kps = orb.detect(gray, None)
    return len(kps or [])


def select_keyframes(
    frames: list[np.ndarray],
    max_frames: int | None = None,
) -> tuple[list[np.ndarray], list[int]]:
    """Walk the video in order. Keep the next sharp, well-exposed frame that still overlaps."""
    if max_frames is None:
        max_frames = int(quality_preset()["max_frames"])
    n = len(frames)
    if n == 0:
        return [], []
    scores = [sharpness(f) for f in frames]
    feats = [_feature_count(f) for f in frames]
    hists = [histogram_signature(f) for f in frames]
    median_s = float(np.median(scores)) if scores else 0.0
    median_f = float(np.median(feats)) if feats else 0.0
    sharp_floor = max(median_s * 0.30, 10.0)
    feat_floor = max(median_f * 0.35, 40.0)

    keep = []
    indices = []
    last = -1
    for i in range(n):
        if len(keep) >= max_frames:
            break
        if not exposure_ok(frames[i]):
            continue
        if scores[i] < sharp_floor or feats[i] < feat_floor:
            continue
        if last >= 0:
            if is_duplicate(hists[last], hists[i], threshold=0.992):
                continue
            move = _motion(frames[last], frames[i])
            if move < 0.10:
                continue
            if move > 22.0:
                continue
            overlap = _orb_matches(frames[last], frames[i])
            if overlap < 28:
                continue
        keep.append(frames[i])
        indices.append(i)
        last = i
    if len(keep) < MIN_FRAMES:
        usable = [i for i in range(n) if exposure_ok(frames[i]) and scores[i] >= sharp_floor]
        if len(usable) < MIN_FRAMES:
            usable = list(range(n))
        pick = [usable[int(i)] for i in np.linspace(0, len(usable) - 1, min(max_frames, len(usable)))]
        pick = sorted(set(int(i) for i in pick))
        return [frames[i] for i in pick], pick
    return keep, indices


def write_frame_quality(path, frames: list[np.ndarray], selected: list[int]) -> None:
    import json
    from pathlib import Path

    chosen = set(selected)
    rows = []
    for i, frame in enumerate(frames):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rows.append(
            {
                "frame": f"candidate_{i:06d}.jpg",
                "sharpness": round(sharpness(frame), 3),
                "features": int(_feature_count(frame)),
                "brightness": round(float(gray.mean()) / 255.0, 3),
                "selected": i in chosen,
            }
        )
    Path(path).write_text(json.dumps(rows, indent=2), encoding="utf-8")
