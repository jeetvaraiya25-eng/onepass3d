from backend.app.api.jobs import health, reconstruction_cancel, reconstruction_result, reconstruction_status
from backend.app.services.storage import new_job, update_job
from backend.pipeline.jobs.job_manager import job_manager


def test_health_includes_colmap():
    body = health()
    assert body["ok"] is True
    assert "colmap" in body
    assert "installed" in body["colmap"]
    assert "ffmpeg" in body


def test_status_and_result_and_cancel():
    record = new_job("API test")
    job_id = record["id"]
    update_job(
        job_id,
        status="running",
        progress={"stage": "dense", "percent": 67, "message": "Running PatchMatch MVS"},
        result={"metrics": {"inputFrames": 180, "registeredFrames": 162, "sparsePoints": 130421}},
    )
    payload = reconstruction_status(job_id)
    assert payload["jobId"] == job_id
    assert payload["stage"] == "dense"
    assert payload["metrics"]["registeredFrames"] == 162

    result = reconstruction_result(job_id)
    assert result["status"] == "running"

    cancelled = reconstruction_cancel(job_id)
    assert cancelled["cancelled"] is True
    job_manager.finish(job_id)
