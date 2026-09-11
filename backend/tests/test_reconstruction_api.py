from backend.app.api.jobs import (
    get_job,
    get_jobs,
    health,
    reconstruction_cancel,
    reconstruction_result,
    reconstruction_status,
)
from backend.app.services.storage import delete_job, job_dir, load_job, new_job, save_job, update_job
from backend.pipeline.jobs.job_manager import job_manager


def test_health_includes_colmap():
    body = health()
    assert body["ok"] is True
    assert "colmap" in body
    assert "installed" in body["colmap"]
    assert "ffmpeg" in body
    assert "timing" in body
    assert body["timing"]["high"]["seconds"] > body["timing"]["normal"]["seconds"]


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
    assert "etaSeconds" in payload
    assert payload["timing"]["percent"] == 67

    result = reconstruction_result(job_id)
    assert result["status"] == "running"

    cancelled = reconstruction_cancel(job_id)
    assert cancelled["cancelled"] is True
    job_manager.finish(job_id)
    delete_job(job_id)


def test_cancel_works_before_worker_starts():
    record = new_job("Cancel early")
    job_id = record["id"]
    cancelled = reconstruction_cancel(job_id)
    assert cancelled["cancelled"] is True
    assert job_manager.is_cancelled(job_id)
    assert load_job(job_id)["status"] == "failed"
    assert load_job(job_id)["cancelled"] is True
    job_manager.finish(job_id)
    delete_job(job_id)


def test_cancelled_flag_is_cleared_on_retry():
    record = new_job("Cancel then resume")
    job_id = record["id"]
    reconstruction_cancel(job_id)
    assert get_job(job_id).cancelled is True
    update_job(job_id, cancelled=False, status="failed")
    assert get_job(job_id).cancelled is False
    job_manager.finish(job_id)
    delete_job(job_id)


def test_job_detail_lists_thumbs_from_disk():
    record = new_job("Thumbs")
    job_id = record["id"]
    folder = job_dir(job_id) / "output" / "thumbs"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "thumb_00.jpg").write_bytes(b"x")
    (folder / "thumb_01.jpg").write_bytes(b"x")
    detail = get_job(job_id)
    assert detail.thumbs == ["thumb_00.jpg", "thumb_01.jpg"]
    delete_job(job_id)


def test_summary_survives_a_job_file_without_new_fields():
    record = new_job("Old record")
    job_id = record["id"]
    stored = load_job(job_id)
    stored.pop("cancelled", None)
    save_job(stored)
    names = {job.id: job for job in get_jobs().jobs}
    assert names[job_id].cancelled is False
    delete_job(job_id)
