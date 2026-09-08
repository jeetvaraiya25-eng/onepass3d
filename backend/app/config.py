from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
DATA_DIR = ROOT_DIR / "data"
JOBS_DIR = DATA_DIR / "jobs"

MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024  # 4K phone/drone clips are often 1–3 GB
MAX_KEYFRAMES = 80
LONG_EDGE = 1080
MIN_FRAMES = 5
MAX_WEB_POINTS = 400_000
WORKER_THREADS = 1

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
TELEMETRY_EXTENSIONS = {".srt", ".csv", ".gpx", ".json", ".txt"}

JOBS_DIR.mkdir(parents=True, exist_ok=True)
