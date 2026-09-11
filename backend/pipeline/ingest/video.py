from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from backend.app.config import IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, MAX_VIDEO_SECONDS, VIDEO_EXTENSIONS, quality_preset


def list_images(folder: Path) -> list[Path]:
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
    return sorted(files, key=lambda p: p.name.lower())


def list_videos(folder: Path) -> list[Path]:
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
    return sorted(files, key=lambda p: p.name.lower())


def resize_long_edge(image: np.ndarray, long_edge: int | None = None) -> np.ndarray:
    if long_edge is None:
        long_edge = int(quality_preset()["max_image_size"] or MAX_IMAGE_SIZE)
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= long_edge:
        return image
    scale = long_edge / float(longest)
    return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def apply_exif_orientation(path: Path) -> np.ndarray | None:
    """Read a photo as BGR, honoring EXIF rotation so phone shots are upright."""
    try:
        with Image.open(path) as pil:
            pil = ImageOps.exif_transpose(pil)
            rgb = np.array(pil.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        return cv2.imread(str(path), cv2.IMREAD_COLOR)


def letterbox(image: np.ndarray, width: int, height: int) -> np.ndarray:
    h, w = image.shape[:2]
    if h == height and w == width:
        return image
    scale = min(width / max(w, 1), height / max(h, 1))
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((height, width, image.shape[2] if image.ndim == 3 else 1), dtype=image.dtype)
    y0 = (height - nh) // 2
    x0 = (width - nw) // 2
    if image.ndim == 2:
        canvas[y0 : y0 + nh, x0 : x0 + nw] = resized
    else:
        canvas[y0 : y0 + nh, x0 : x0 + nw] = resized
    return canvas


def unify_frame_sizes(frames: list[np.ndarray]) -> list[np.ndarray]:
    """Optical flow and a shared camera matrix need every frame the same size."""
    if not frames:
        return frames
    shapes = {frame.shape[:2] for frame in frames}
    if len(shapes) == 1:
        return frames
    height = int(max(frame.shape[0] for frame in frames))
    width = int(max(frame.shape[1] for frame in frames))
    return [letterbox(frame, width, height) for frame in frames]


def extract_video_candidates(
    video_path: Path,
    target: int = 200,
    on_progress=None,
) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path.name}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    duration = (total / fps) if fps > 1e-3 else 0.0
    if duration > MAX_VIDEO_SECONDS:
        cap.release()
        raise RuntimeError(
            f"This video is {duration:.0f}s long. Upload a clip shorter than {MAX_VIDEO_SECONDS}s."
        )
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    if width >= 2500:
        target = min(target, max(220, int(quality_preset()["candidate_frames"])))
    step = max(1, (total // target) if total > 0 else 8)
    frames: list[np.ndarray] = []
    index = 0
    while len(frames) < target:
        if index % step != 0:
            if not cap.grab():
                break
            index += 1
            continue
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(resize_long_edge(frame))
        if on_progress:
            on_progress(len(frames), target, video_path.name)
        index += 1
    cap.release()
    if not frames:
        raise RuntimeError("Video contained no readable frames.")
    return frames


def save_frames(frames: list[np.ndarray], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, frame in enumerate(frames):
        path = output_dir / f"frame_{i:04d}.jpg"
        cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        paths.append(path)
    return paths


def load_photo_frames(paths: list[Path]) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    for path in paths:
        image = apply_exif_orientation(path)
        if image is None:
            continue
        frames.append(image)
    if not frames:
        raise RuntimeError("None of the uploaded photos could be read.")
    return frames


def collect_source_frames(input_dir: Path, on_progress=None) -> list[np.ndarray]:
    photos = list_images(input_dir)
    videos = list_videos(input_dir)
    frames: list[np.ndarray] = []
    if photos:
        frames.extend([resize_long_edge(frame) for frame in load_photo_frames(photos)])
    for video in videos:
        frames.extend(
            extract_video_candidates(
                video,
                target=int(quality_preset()["candidate_frames"]),
                on_progress=on_progress,
            )
        )
    if not frames:
        raise RuntimeError("Upload a drone video or at least 5 photos from a single pass.")
    return unify_frame_sizes(frames)
