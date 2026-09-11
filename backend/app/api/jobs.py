from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.app.config import MAX_UPLOAD_BYTES, normalize_quality
from backend.pipeline.jobs.job_manager import job_manager
from backend.pipeline.reconstruct.deps import check_dependencies
from backend.pipeline.reconstruct.colmap.detector import check_colmap_installation
from backend.app.models.schemas import JobDetail, JobList, JobSummary
from backend.app.services.storage import (
    classify_upload,
    delete_job,
    job_dir,
    list_jobs,
    load_job,
    new_job,
    update_job,
)
from backend.pipeline.demo.real_splat import DEFAULT_SCENE, SCENES, list_scenes, splat_path
from backend.app.workers.pipeline_worker import enqueue, run_now
from backend.pipeline.export.glb import fix_glb_json_padding, glb_json_has_null_padding


router = APIRouter(prefix="/api")


def _summary(record: dict) -> JobSummary:
    return JobSummary(**{k: record[k] for k in JobSummary.model_fields})


def _detail(record: dict) -> JobDetail:
    return JobDetail(**{k: record.get(k) for k in JobDetail.model_fields})


@router.get("/health")
def health() -> dict:
    deps = check_dependencies()
    return {
        "ok": True,
        "name": "OnePass3D",
        **deps,
    }


@router.get("/colmap")
def colmap_status() -> dict:
    return check_colmap_installation()


@router.get("/jobs", response_model=JobList)
def get_jobs() -> JobList:
    return JobList(jobs=[_summary(job) for job in list_jobs()])


@router.post("/jobs", response_model=JobDetail)
async def create_job(
    files: list[UploadFile] = File(...),
    name: str = Form("Untitled flight"),
    quality: str = Form("normal"),
) -> JobDetail:
    if not files:
        raise HTTPException(400, "Upload a drone video or photos.")

    record = new_job(name=name.strip() or "Untitled flight")
    dest = job_dir(record["id"]) / "input"
    saved = []
    kinds = set()
    total = 0
    for upload in files:
        filename = Path(upload.filename or "upload.bin").name
        kind = classify_upload(filename)
        if kind is None:
            delete_job(record["id"])
            raise HTTPException(400, f"Unsupported file: {filename}")
        data = await upload.read()
        total += len(data)
        if total > MAX_UPLOAD_BYTES:
            delete_job(record["id"])
            raise HTTPException(413, "Upload exceeds 4 GB. Export a shorter clip or a 1080p copy.")
        (dest / filename).write_bytes(data)
        saved.append(filename)
        kinds.add(kind)

    if "video" not in kinds and "image" not in kinds:
        delete_job(record["id"])
        raise HTTPException(400, "Include a video or photos. Telemetry alone is not enough.")

    update_job(
        record["id"],
        input_files=saved,
        name=name.strip() or saved[0],
        quality=normalize_quality(quality),
    )
    enqueue(record["id"])
    return _detail(load_job(record["id"]))


@router.get("/examples")
def get_examples() -> dict:
    return {"scenes": list_scenes()}


@router.get("/samples/{name}")
def get_sample_file(name: str):
    key = Path(name).stem.lower()
    if Path(name).suffix.lower() != ".splat" or key not in SCENES:
        raise HTTPException(404, "Unknown sample")
    path = splat_path(key)
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Sample not on disk")
    return FileResponse(path, media_type="application/octet-stream")


@router.post("/jobs/demo", response_model=JobDetail)
def create_demo(scene: str = DEFAULT_SCENE) -> JobDetail:
    key = (scene or DEFAULT_SCENE).strip().lower()
    if key not in SCENES:
        raise HTTPException(400, f"Unknown sample scene. Try: {', '.join(SCENES)}")
    for existing in list_jobs():
        if (
            existing.get("is_demo")
            and existing.get("demo_scene") == key
            and existing.get("status") == "done"
        ):
            return _detail(existing)
    meta = SCENES[key]
    record = new_job(name=meta["job_name"])
    update_job(
        record["id"],
        is_demo=True,
        demo_scene=key,
        input_files=[f"sample://{key}"],
    )
    run_now(record["id"])
    return _detail(load_job(record["id"]))


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: str) -> JobDetail:
    try:
        return _detail(load_job(job_id))
    except FileNotFoundError:
        raise HTTPException(404, "Job not found")


@router.delete("/jobs/{job_id}")
def remove_job(job_id: str) -> dict:
    try:
        load_job(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Job not found")
    delete_job(job_id)
    return {"ok": True}


@router.api_route("/jobs/{job_id}/files/{filename}", methods=["GET", "HEAD"])
def get_file(job_id: str, filename: str):
    try:
        load_job(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Job not found")
    safe = Path(filename).name
    for folder in ("output", "output/thumbs", "work/frames"):
        path = job_dir(job_id) / folder / safe
        if path.exists() and path.is_file():
            media = "application/octet-stream"
            if safe.endswith(".jpg") or safe.endswith(".jpeg"):
                media = "image/jpeg"
            elif safe.endswith(".png"):
                media = "image/png"
            elif safe.endswith(".json"):
                media = "application/json"
            elif safe.endswith(".glb"):
                media = "model/gltf-binary"
                if glb_json_has_null_padding(path):
                    fix_glb_json_padding(path)
            elif safe.endswith(".gltf"):
                media = "model/gltf+json"
            elif safe.endswith(".splat") or safe.endswith(".ksplat"):
                media = "application/octet-stream"
            # Do not set filename= — Safari treats attachment downloads as
            # a save dialog and the splat viewer never receives the bytes.
            headers = {"X-Content-Type-Options": "nosniff"}
            if safe.endswith(".glb"):
                headers["Content-Type"] = "model/gltf-binary"
            return FileResponse(path, media_type=media, headers=headers)
    raise HTTPException(404, "File not found")


def _job_or_404(job_id: str) -> dict:
    try:
        return load_job(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Job not found")


@router.get("/reconstruction/{job_id}/status")
def reconstruction_status(job_id: str) -> dict:
    record = _job_or_404(job_id)
    result = record.get("result") or {}
    metrics = result.get("metrics") or {}
    progress = record.get("progress") or {}
    return {
        "jobId": record["id"],
        "stage": progress.get("stage") or record.get("status"),
        "progress": progress.get("percent") or 0,
        "status": record.get("status"),
        "message": progress.get("message") or record.get("error") or "",
        "metrics": metrics,
    }


@router.get("/reconstruction/{job_id}/result")
def reconstruction_result(job_id: str) -> dict:
    record = _job_or_404(job_id)
    result = record.get("result") or {}
    metrics = result.get("metrics") or {}
    if record.get("status") != "done":
        return {
            "status": record.get("status"),
            "modelUrl": None,
            "pointCloudUrl": None,
            "previewUrl": None,
            "metrics": metrics,
            "error": record.get("error"),
        }
    return {
        "status": "completed",
        "modelUrl": f"/api/jobs/{job_id}/files/model.glb",
        "pointCloudUrl": f"/api/jobs/{job_id}/files/pointcloud.ply",
        "previewUrl": f"/api/jobs/{job_id}/files/preview.jpg",
        "metrics": metrics,
    }


@router.post("/reconstruction/{job_id}/retry", response_model=JobDetail)
def reconstruction_retry(job_id: str) -> JobDetail:
    record = _job_or_404(job_id)
    if record.get("status") == "running":
        raise HTTPException(409, "This job is already running.")
    update_job(
        job_id,
        status="queued",
        error=None,
        progress={"stage": "queued", "percent": 0, "message": "Resuming from the last finished stage"},
        log="Retry requested — resuming from saved stages",
    )
    enqueue(job_id)
    return _detail(load_job(job_id))


@router.post("/reconstruction/{job_id}/cancel")
def reconstruction_cancel(job_id: str) -> dict:
    record = _job_or_404(job_id)
    if record.get("status") in {"done", "failed"}:
        return {"ok": True, "status": record["status"], "cancelled": False}
    cancelled = job_manager.cancel(job_id)
    update_job(
        job_id,
        status="failed",
        error="Reconstruction was cancelled.",
        progress={"stage": "failed", "percent": 0, "message": "Reconstruction was cancelled."},
        log="Cancellation requested",
    )
    return {"ok": True, "status": "failed", "cancelled": cancelled or True}


@router.get("/reconstruction/{job_id}/model.glb")
def reconstruction_model(job_id: str):
    return get_file(job_id, "model.glb")
