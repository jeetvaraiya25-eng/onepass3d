from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from backend.app.config import IMAGE_EXTENSIONS, JOBS_DIR, TELEMETRY_EXTENSIONS, VIDEO_EXTENSIONS


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def new_job(name: str) -> dict[str, Any]:
    job_id = uuid4().hex[:12]
    path = job_dir(job_id)
    (path / "input").mkdir(parents=True, exist_ok=True)
    (path / "work" / "frames").mkdir(parents=True, exist_ok=True)
    (path / "output").mkdir(parents=True, exist_ok=True)
    record = {
        "id": job_id,
        "name": name,
        "status": "queued",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "progress": {"stage": "queued", "percent": 0, "message": "Waiting to start"},
        "error": None,
        "has_gps": False,
        "frame_count": 0,
        "point_count": 0,
        "triangle_count": 0,
        "metric": False,
        "input_files": [],
        "logs": [],
        "result": None,
        "is_demo": False,
        "quality": "normal",
        "started_at": None,
        "duration_sec": 0,
        "cancelled": False,
    }
    save_job(record)
    return record


def job_json_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.json"


def save_job(record: dict[str, Any]) -> None:
    record["updated_at"] = utc_now()
    path = job_json_path(record["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_job(job_id: str) -> dict[str, Any]:
    path = job_json_path(job_id)
    if not path.exists():
        raise FileNotFoundError(job_id)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise FileNotFoundError(job_id)
    return json.loads(text)


def list_jobs() -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    if not JOBS_DIR.exists():
        return jobs
    for child in JOBS_DIR.iterdir():
        meta = child / "job.json"
        if meta.exists():
            jobs.append(json.loads(meta.read_text(encoding="utf-8")))
    jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return jobs


def update_job(job_id: str, **fields: Any) -> dict[str, Any]:
    record = load_job(job_id)
    logs = fields.pop("log", None)
    progress = fields.pop("progress", None)
    if logs:
        record.setdefault("logs", []).append(logs)
        record["logs"] = record["logs"][-80:]
    if progress:
        record["progress"] = {**record.get("progress", {}), **progress}
    record.update(fields)
    save_job(record)
    return record


def delete_job(job_id: str) -> None:
    path = job_dir(job_id)
    if path.exists():
        shutil.rmtree(path)


def classify_upload(filename: str) -> Optional[str]:
    suffix = Path(filename).suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in TELEMETRY_EXTENSIONS:
        return "telemetry"
    return None
