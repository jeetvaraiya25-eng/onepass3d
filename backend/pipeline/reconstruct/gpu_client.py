from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def worker_url() -> str:
    return (os.environ.get("RECON_WORKER_URL") or "").strip().rstrip("/")


def try_remote_reconstruction(job_id: str, frames_dir: Path, output_dir: Path) -> bool:
    """
    Optional CUDA / COLMAP box. The website never needs an NVIDIA GPU.
    Set RECON_WORKER_URL to a worker (friend's PC or a cloud GPU).
    """
    base = worker_url()
    if not base:
        return False
    files = sorted(frames_dir.glob("frame_*.jpg"))
    if len(files) < 5:
        return False
    boundary = "----onepass3d"
    body = bytearray()
    for path in files[:120]:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="files"; filename="{path.name}"\r\n'.encode()
        )
        body.extend(b"Content-Type: image/jpeg\r\n\r\n")
        body.extend(path.read_bytes())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"{base}/jobs?job_id={job_id}",
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False
    remote_id = meta.get("id") or job_id
    deadline = time.time() + 45 * 60
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/jobs/{remote_id}", timeout=30) as resp:
                status = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return False
        if status.get("status") == "failed":
            raise RuntimeError(status.get("error") or "GPU worker failed reconstruction.")
        if status.get("status") == "done":
            glb = _fetch(f"{base}/jobs/{remote_id}/files/model.glb")
            if not glb:
                return False
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "model.glb").write_bytes(glb)
            mesh = _fetch(f"{base}/jobs/{remote_id}/files/mesh.obj")
            if mesh:
                (output_dir / "mesh.obj").write_bytes(mesh)
            cloud = _fetch(f"{base}/jobs/{remote_id}/files/pointcloud.ply")
            if cloud:
                (output_dir / "pointcloud.ply").write_bytes(cloud)
            return True
        time.sleep(4)
    return False


def _fetch(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            if resp.status != 200:
                return None
            return resp.read()
    except (urllib.error.URLError, TimeoutError):
        return None
