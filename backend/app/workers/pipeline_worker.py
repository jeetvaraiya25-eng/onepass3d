from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from backend.app.config import WORKER_THREADS
from backend.app.services.errors import explain_failure
from backend.app.services.storage import update_job
from backend.pipeline.reconstruct.colmap.runner import ColmapCancelled
from backend.pipeline.run import run_job


_executor = ThreadPoolExecutor(max_workers=WORKER_THREADS)


def _safe_run(job_id: str) -> None:
    try:
        run_job(job_id)
    except FileNotFoundError:
        return
    except ColmapCancelled:
        message = "Reconstruction was cancelled."
        update_job(
            job_id,
            status="failed",
            error=message,
            progress={"stage": "failed", "percent": 0, "message": message},
            log=message,
        )
        return
    except Exception as exc:
        message = explain_failure(exc)
        update_job(
            job_id,
            status="failed",
            error=message,
            progress={"stage": "failed", "percent": 0, "message": message},
            log=f"{message} ({type(exc).__name__}: {exc})",
        )


def enqueue(job_id: str) -> None:
    _executor.submit(_safe_run, job_id)


def run_now(job_id: str) -> None:
    """Examples must not wait behind a 4K upload on the single worker."""
    _safe_run(job_id)
