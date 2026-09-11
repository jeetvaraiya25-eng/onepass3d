from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
DATA_DIR = ROOT_DIR / "data"
JOBS_DIR = DATA_DIR / "jobs"

MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024  # 4K phone/drone clips are often 1–3 GB
MAX_KEYFRAMES = int(os.environ.get("ONEPASS_MAX_KEYFRAMES", "180"))
LONG_EDGE = int(os.environ.get("ONEPASS_LONG_EDGE", os.environ.get("MAX_IMAGE_SIZE", "2000")))
MAX_IMAGE_SIZE = int(os.environ.get("MAX_IMAGE_SIZE", str(LONG_EDGE)))
MIN_FRAMES = 5
MAX_WEB_POINTS = 400_000
DENSE_GRID = int(os.environ.get("ONEPASS_DENSE_GRID", "128"))
DENSE_SPANS = tuple(int(x) for x in os.environ.get("ONEPASS_DENSE_SPANS", "1,2,3").split(",") if x.strip())
WORKER_THREADS = 1
RECON_WORKER_URL = (os.environ.get("RECON_WORKER_URL") or "").strip()

COLMAP_PATH = (os.environ.get("COLMAP_PATH") or "").strip()
OPENMVS_PATH = (os.environ.get("OPENMVS_PATH") or "").strip()
FFMPEG_PATH = (os.environ.get("FFMPEG_PATH") or "").strip()
FEATURE_THREADS = int(os.environ.get("FEATURE_THREADS", "0"))
MAX_DENSE_IMAGE_SIZE = int(os.environ.get("MAX_DENSE_IMAGE_SIZE", "2000"))
DENSE_BACKEND = (os.environ.get("DENSE_BACKEND") or "auto").strip().lower()
RECONSTRUCTION_DEVICE = (os.environ.get("RECONSTRUCTION_DEVICE") or "auto").strip().lower()
RECONSTRUCTION_QUALITY = (os.environ.get("RECONSTRUCTION_QUALITY") or "medium").strip().lower()
RECONSTRUCTION_DEBUG = (os.environ.get("RECONSTRUCTION_DEBUG") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MESH_METHOD = (os.environ.get("MESH_METHOD") or "poisson").strip().lower()
MESH_FACE_RATIO = float(os.environ.get("MESH_FACE_RATIO", "0.25"))
MIN_REGISTRATION_RATIO = float(os.environ.get("MIN_REGISTRATION_RATIO", "0.60"))
PREFERRED_REGISTRATION_RATIO = float(os.environ.get("PREFERRED_REGISTRATION_RATIO", "0.75"))
MAX_REPROJ_ERROR = float(os.environ.get("MAX_REPROJ_ERROR", "3.0"))
MIN_SPARSE_POINTS = int(os.environ.get("MIN_SPARSE_POINTS", "800"))
MIN_DENSE_POINTS = int(os.environ.get("MIN_DENSE_POINTS", "20000"))
MAX_VIDEO_SECONDS = int(os.environ.get("MAX_VIDEO_SECONDS", "600"))
COLMAP_STAGE_TIMEOUT = int(os.environ.get("COLMAP_STAGE_TIMEOUT", "7200"))
COLMAP_JOB_TIMEOUT = int(os.environ.get("COLMAP_JOB_TIMEOUT", "21600"))

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
TELEMETRY_EXTENSIONS = {".srt", ".csv", ".gpx", ".json", ".txt"}

QUALITY_PRESETS = {
    "low": {
        "candidate_frames": 160,
        "max_frames": 80,
        "max_image_size": min(1200, MAX_IMAGE_SIZE),
        "match_overlap": 12,
        "face_ratio": min(0.35, MESH_FACE_RATIO),
        "prefer_photo_texture": False,
    },
    "normal": {
        "candidate_frames": 240,
        "max_frames": min(100, MAX_KEYFRAMES),
        "max_image_size": min(1400, MAX_IMAGE_SIZE),
        "match_overlap": 12,
        "face_ratio": MESH_FACE_RATIO,
        "prefer_photo_texture": False,
    },
    "medium": {
        "candidate_frames": 320,
        "max_frames": min(180, MAX_KEYFRAMES),
        "max_image_size": min(1600, MAX_IMAGE_SIZE),
        "match_overlap": 16,
        "face_ratio": MESH_FACE_RATIO,
        "prefer_photo_texture": False,
    },
    "high": {
        "candidate_frames": 480,
        "max_frames": min(250, max(MAX_KEYFRAMES, 220)),
        "max_image_size": MAX_IMAGE_SIZE,
        "match_overlap": 20,
        "face_ratio": MESH_FACE_RATIO,
        "prefer_photo_texture": False,
    },
}

_active_quality: str | None = None


def normalize_quality(name: str | None = None) -> str:
    key = (name or _active_quality or RECONSTRUCTION_QUALITY or "normal").strip().lower()
    aliases = {
        "fast": "normal",
        "standard": "normal",
        "default": "normal",
        "higher": "high",
        "higher_detail": "high",
        "detail": "high",
    }
    return aliases.get(key, key if key in QUALITY_PRESETS else "normal")


def apply_job_quality(name: str | None) -> str:
    global _active_quality
    _active_quality = normalize_quality(name)
    return _active_quality


def quality_preset(name: str | None = None) -> dict:
    return QUALITY_PRESETS.get(normalize_quality(name), QUALITY_PRESETS["normal"])


JOBS_DIR.mkdir(parents=True, exist_ok=True)
