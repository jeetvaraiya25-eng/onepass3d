#!/usr/bin/env python3
"""
Optional CUDA reconstruction worker.

Run this on a machine that has NVIDIA CUDA + COLMAP (friend's laptop or a cloud GPU).
The website only needs RECON_WORKER_URL pointing here.

  pip install fastapi uvicorn python-multipart
  uvicorn gpu_worker.server:app --host 0.0.0.0 --port 8090
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse

app = FastAPI(title="OnePass3D GPU worker")
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()


def _job_dir(job_id: str) -> Path:
    root = Path(tempfile.gettempdir()) / "onepass3d-worker" / job_id
    (root / "images").mkdir(parents=True, exist_ok=True)
    (root / "output").mkdir(parents=True, exist_ok=True)
    return root


@app.post("/jobs")
async def create_job(job_id: str = "", files: list[UploadFile] = File(...)) -> dict:
    job_id = job_id or uuid.uuid4().hex[:12]
    root = _job_dir(job_id)
    for upload in files:
        data = await upload.read()
        (root / "images" / Path(upload.filename or "frame.jpg").name).write_bytes(data)
    with LOCK:
        JOBS[job_id] = {"id": job_id, "status": "queued", "error": ""}
    threading.Thread(target=_run, args=(job_id,), daemon=True).start()
    return {"id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return JOBS.get(job_id, {"id": job_id, "status": "failed", "error": "Unknown job"})


@app.get("/jobs/{job_id}/files/{name}")
def get_file(job_id: str, name: str):
    path = _job_dir(job_id) / "output" / Path(name).name
    if not path.exists():
        return FileResponse(path, status_code=404)
    return FileResponse(path)


def _run(job_id: str) -> None:
    with LOCK:
        JOBS[job_id]["status"] = "running"
    root = _job_dir(job_id)
    try:
        colmap = shutil.which("colmap")
        if not colmap:
            raise RuntimeError(
                "COLMAP is not installed on this GPU worker. "
                "Install COLMAP with CUDA, then restart the worker."
            )
        images = root / "images"
        db = root / "database.db"
        sparse = root / "sparse"
        dense = root / "dense"
        sparse.mkdir(exist_ok=True)
        _call([colmap, "feature_extractor", "--database_path", str(db), "--image_path", str(images)])
        _call([colmap, "sequential_matcher", "--database_path", str(db)])
        _call(
            [
                colmap,
                "mapper",
                "--database_path",
                str(db),
                "--image_path",
                str(images),
                "--output_path",
                str(sparse),
            ]
        )
        model = next((p for p in sparse.iterdir() if p.is_dir()), None)
        if model is None:
            raise RuntimeError("COLMAP could not reconstruct camera poses from these frames.")
        _call(
            [
                colmap,
                "image_undistorter",
                "--image_path",
                str(images),
                "--input_path",
                str(model),
                "--output_path",
                str(dense),
                "--output_type",
                "COLMAP",
            ]
        )
        try:
            _call([colmap, "patch_match_stereo", "--workspace_path", str(dense)])
            _call([colmap, "stereo_fusion", "--workspace_path", str(dense), "--output_path", str(dense / "fused.ply")])
            _call(
                [
                    colmap,
                    "poisson_mesher",
                    "--input_path",
                    str(dense / "fused.ply"),
                    "--output_path",
                    str(root / "output" / "mesh.ply"),
                ]
            )
        except RuntimeError:
            # No CUDA stereo — still fail honestly rather than return dots.
            raise RuntimeError(
                "COLMAP is installed but dense stereo needs an NVIDIA GPU with CUDA. "
                "Run this worker on a CUDA machine."
            )
        mesh = root / "output" / "mesh.ply"
        if not mesh.exists():
            raise RuntimeError("COLMAP did not write a mesh.")
        # Leave conversion to the main app if only PLY is present; copy as model marker.
        shutil.copy2(mesh, root / "output" / "model.glb") if mesh.suffix == ".glb" else None
        if not (root / "output" / "model.glb").exists():
            # Worker without GLB converter: the site still needs GLB. Convert via a tiny local import if available.
            try:
                from backend.pipeline.export.glb import write_glb
                from backend.pipeline.export.ply import read_ascii_ply  # may not exist
            except Exception:
                shutil.copy2(mesh, root / "output" / "pointcloud.ply")
                raise RuntimeError("Worker wrote a mesh PLY but could not convert it to GLB.")
        with LOCK:
            JOBS[job_id]["status"] = "done"
    except Exception as exc:
        with LOCK:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(exc)


def _call(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "COLMAP command failed")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8090)
