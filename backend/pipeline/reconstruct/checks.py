from __future__ import annotations

import cv2
import numpy as np

from backend.pipeline.ingest.quality import histogram_signature, sharpness


def assess_frames(frames: list[np.ndarray]) -> None:
    """Fail with a useful message instead of returning a cloud of dots."""
    if len(frames) < 5:
        raise RuntimeError(
            "Need at least 5 sharp, distinct frames. Got "
            f"{len(frames)}. Upload a longer single-pass orbit, not a still hover."
        )
    scores = [sharpness(f) for f in frames]
    median = float(np.median(scores)) if scores else 0.0
    if median < 18.0:
        raise RuntimeError(
            "The video is too blurry for reconstruction. Slow the drone down, "
            "avoid fast yaw, and fly in good light so edges stay sharp."
        )
    hists = [histogram_signature(f) for f in frames]
    unique = 1
    for i in range(1, len(hists)):
        a = hists[i].astype(np.float64).ravel()
        b = hists[i - 1].astype(np.float64).ravel()
        sim = float(a @ b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8)
        if sim < 0.985:
            unique += 1
    if unique < 4:
        raise RuntimeError(
            "Almost every frame shows the same viewpoint. The drone barely moved. "
            "Fly a slow circle or a straight pass so the camera sees new angles."
        )
    gray = cv2.cvtColor(frames[len(frames) // 2], cv2.COLOR_BGR2GRAY)
    if float(np.std(gray)) < 8.0:
        raise RuntimeError(
            "These frames have almost no visual features (blank sky, water, or fog). "
            "Aim the camera at buildings, roads, or textured ground."
        )


def assess_geometry(xyz: np.ndarray, pair_count: int) -> None:
    if len(xyz) < 200:
        raise RuntimeError(
            "3D reconstruction could not produce a reliable surface from this video."
        )
    if pair_count < 3:
        raise RuntimeError("Camera reconstruction failed")
