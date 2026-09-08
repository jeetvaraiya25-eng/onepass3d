from __future__ import annotations

import cv2
import numpy as np


def motion_masks(frames: list[np.ndarray], thresh: int = 28) -> list[np.ndarray]:
    """Binary masks (255 = likely moving object). Ignores whole-frame camera motion."""
    masks: list[np.ndarray] = []
    kernel = np.ones((5, 5), np.uint8)
    for i in range(len(frames) - 1):
        a = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
        b = cv2.cvtColor(frames[i + 1], cv2.COLOR_BGR2GRAY)
        if a.shape != b.shape:
            b = cv2.resize(b, (a.shape[1], a.shape[0]))
        delta = cv2.absdiff(a, b)
        _, mask = cv2.threshold(delta, thresh, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.dilate(mask, kernel, iterations=1)
        # Camera translation lights up most of the frame; keep only compact blobs.
        if (mask > 0).mean() > 0.12:
            mask = np.zeros_like(mask)
        masks.append(mask)
    return masks
