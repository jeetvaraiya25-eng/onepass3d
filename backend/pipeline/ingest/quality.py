from __future__ import annotations

import cv2
import numpy as np

from backend.app.config import MAX_KEYFRAMES, MIN_FRAMES


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


def select_keyframes(frames: list[np.ndarray], max_frames: int = MAX_KEYFRAMES) -> tuple[list[np.ndarray], list[int]]:
    n = len(frames)
    if n <= max_frames:
        sharp = [sharpness(f) for f in frames]
        median = float(np.median(sharp)) if sharp else 0.0
        keep = []
        indices = []
        for i, (frame, score) in enumerate(zip(frames, sharp)):
            if score >= median * 0.35 or n <= MIN_FRAMES:
                keep.append(frame)
                indices.append(i)
        if len(keep) < min(MIN_FRAMES, n):
            return frames, list(range(n))
        return keep, indices

    # Prefer even spacing so an orbit is not collapsed to near-duplicate sky frames.
    pick = sorted({int(i) for i in np.linspace(0, n - 1, max_frames)})
    sharp = [sharpness(frames[i]) for i in pick]
    median = float(np.median(sharp)) if sharp else 0.0
    keep = []
    indices = []
    for i, score in zip(pick, sharp):
        if score >= median * 0.2 or len(pick) <= MIN_FRAMES:
            keep.append(frames[i])
            indices.append(i)
    if len(keep) < MIN_FRAMES:
        return [frames[i] for i in pick], pick
    return keep, indices
