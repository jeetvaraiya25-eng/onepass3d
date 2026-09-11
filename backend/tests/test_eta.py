from backend.app.services.eta import estimate_seconds, format_duration, format_range, job_timing


def test_format_duration_and_range():
    assert format_duration(20) == "under a minute"
    assert format_duration(60) == "1 minute"
    assert "minutes" in format_duration(12 * 60)
    assert format_range(40 * 60, 75 * 60) == "40–75 minutes"
    assert "hours" in format_range(2 * 3600, 4 * 3600)


def test_high_detail_is_slower_than_normal():
    normal = estimate_seconds("normal")
    high = estimate_seconds("high")
    assert high["seconds"] > normal["seconds"] * 2
    assert "hour" in high["range_label"]


def test_longer_video_raises_estimate():
    short = estimate_seconds("normal", duration_sec=60)
    long = estimate_seconds("normal", duration_sec=480)
    assert long["seconds"] > short["seconds"]


def test_job_timing_uses_percent_for_remaining():
    timing = job_timing(
        {
            "quality": "normal",
            "status": "running",
            "frame_count": 80,
            "started_at": "2099-01-01T00:00:00+00:00",
            "created_at": "2099-01-01T00:00:00+00:00",
            "progress": {"stage": "dense", "percent": 50, "message": "Dense"},
        }
    )
    assert timing["percent"] == 50
    assert timing["remaining_seconds"] > 0
    assert timing["quality_label"] == "Normal"


def test_a_job_running_far_over_the_estimate_does_not_claim_it_is_nearly_done():
    from datetime import datetime, timedelta, timezone

    prior = estimate_seconds("normal", photo_count=72)["seconds"]
    started = datetime.now(timezone.utc) - timedelta(seconds=prior * 1.2)
    timing = job_timing(
        {
            "quality": "normal",
            "status": "running",
            "frame_count": 72,
            "started_at": started.isoformat(),
            "created_at": started.isoformat(),
            "progress": {"stage": "matching", "percent": 42, "message": "Matching"},
        }
    )
    # 42% done after more than the whole estimate means well over an hour of work left
    assert timing["remaining_seconds"] > 20 * 60
    assert timing["slow"] is True
    assert timing["remaining_label"] != "under a minute"
