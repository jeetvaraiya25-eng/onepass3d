import numpy as np

from backend.pipeline.ingest.quality import exposure_ok, select_keyframes
from backend.pipeline.ingest.video import resize_long_edge


def _frame(value: int, size: int = 80, noise: float = 8.0) -> np.ndarray:
    rng = np.random.default_rng(value)
    img = np.full((size, size, 3), value, dtype=np.uint8)
    img = np.clip(img.astype(np.float32) + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)
    # Add a moving textured square so frames are not identical.
    x = (value * 3) % (size - 16)
    img[10:26, x : x + 16] = (40, 180, 90)
    return img


def test_rejects_dark_and_overexposed():
    dark = np.zeros((40, 40, 3), dtype=np.uint8)
    bright = np.full((40, 40, 3), 255, dtype=np.uint8)
    ok = _frame(90)
    assert exposure_ok(dark) is False
    assert exposure_ok(bright) is False
    assert exposure_ok(ok) is True


def test_selects_continuous_subset():
    frames = [_frame(40 + i * 6) for i in range(30)]
    kept, idx = select_keyframes(frames, max_frames=12)
    assert len(kept) >= 5
    assert idx == sorted(idx)
    assert idx[-1] > idx[0]


def test_resize_does_not_upscale():
    small = np.zeros((512, 910, 3), dtype=np.uint8)
    out = resize_long_edge(small, long_edge=2000)
    assert out.shape[:2] == (512, 910)
