from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.config import normalize_quality

# Typical 3–5 minute 4K orbit on this Apple silicon Mac (CPU COLMAP + OpenMVS).
REF_VIDEO_SECONDS = 240
REF_PHOTO_COUNT = 80
BASE_SECONDS = {
    "low": 40 * 60,
    "normal": 55 * 60,
    "medium": 90 * 60,
    "high": 3 * 60 * 60,
}
QUALITY_LABELS = {
    "low": "Faster",
    "normal": "Normal",
    "medium": "Medium",
    "high": "Higher detail",
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def format_duration(seconds: float) -> str:
    sec = max(0, int(round(seconds)))
    if sec < 45:
        return "under a minute"
    minutes = int(round(sec / 60))
    if minutes < 60:
        return "1 minute" if minutes == 1 else f"{minutes} minutes"
    hours = minutes // 60
    rest = minutes % 60
    if rest == 0:
        return "1 hour" if hours == 1 else f"{hours} hours"
    if hours == 1:
        return f"1 hr {rest} min"
    return f"{hours} hr {rest} min"


def format_range(low: float, high: float) -> str:
    low_m = max(1, int(round(low / 60)))
    high_m = max(low_m + 1, int(round(high / 60)))
    if high_m < 90:
        return f"{low_m}–{high_m} minutes"
    low_h = max(1, int(round(low / 3600)))
    high_h = max(low_h + 1, int(round(high / 3600)))
    if low_h == high_h:
        return f"about {low_h} hours" if low_h > 1 else "about 1 hour"
    return f"{low_h}–{high_h} hours"


def input_scale(duration_sec: float = 0, photo_count: int = 0) -> float:
    if duration_sec and duration_sec > 0:
        return _clamp(float(duration_sec) / REF_VIDEO_SECONDS, 0.5, 2.4)
    if photo_count and photo_count > 0:
        return _clamp(float(photo_count) / REF_PHOTO_COUNT, 0.5, 2.4)
    return 1.0


def estimate_seconds(quality: str | None, duration_sec: float = 0, photo_count: int = 0) -> dict[str, Any]:
    key = normalize_quality(quality)
    mid = BASE_SECONDS.get(key, BASE_SECONDS["normal"]) * input_scale(duration_sec, photo_count)
    low = mid * 0.75
    high = mid * 1.35
    return {
        "quality": key,
        "quality_label": QUALITY_LABELS.get(key, "Normal"),
        "seconds": int(round(mid)),
        "low_seconds": int(round(low)),
        "high_seconds": int(round(high)),
        "range_label": format_range(low, high),
        "note": "on this Mac, for a typical orbit",
    }


def quality_timing_catalog() -> dict[str, dict[str, Any]]:
    return {
        "normal": {**estimate_seconds("normal"), "note": "on this Mac, for a 3–5 minute orbit"},
        "high": {**estimate_seconds("high"), "note": "on this Mac, for a 3–5 minute orbit"},
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def job_timing(record: dict[str, Any]) -> dict[str, Any]:
    quality = normalize_quality(record.get("quality") or "normal")
    prior = estimate_seconds(
        quality,
        duration_sec=float(record.get("duration_sec") or 0),
        photo_count=int(record.get("frame_count") or 0),
    )
    status = record.get("status") or "queued"
    progress = record.get("progress") or {}
    percent = int(progress.get("percent") or 0)
    if status == "failed":
        percent = 0
    if status == "done":
        percent = 100
    percent = max(0, min(100, percent))

    started = _parse_iso(record.get("started_at")) or _parse_iso(record.get("created_at"))
    elapsed = 0.0
    if started and status in {"running", "queued", "done"}:
        elapsed = max(0.0, (datetime.now(timezone.utc) - started).total_seconds())
    if status == "queued":
        elapsed = 0.0

    total = float(prior["seconds"])
    slow = False
    if status == "running" and percent >= 12 and elapsed > 90:
        pace_total = elapsed / max(percent / 100.0, 0.01)
        if 0.4 * prior["seconds"] <= pace_total <= 2.2 * prior["seconds"]:
            weight = min(0.8, (percent - 12) / 45)
            total = prior["seconds"] * (1 - weight) + pace_total * weight
        else:
            # the run is well outside the estimate: trust what we measured instead of
            # pinning the finish line to "any second now"
            total = _clamp(pace_total, prior["seconds"] * 0.4, prior["seconds"] * 5)
            slow = pace_total > prior["seconds"]
    elif status == "running" and elapsed > prior["seconds"]:
        total = elapsed * 1.5
        slow = True

    if status == "done":
        remaining = 0.0
        total = max(elapsed, 1.0)
    elif status == "failed":
        remaining = 0.0
    else:
        total = max(elapsed + 60, total)
        remaining = 0.0 if percent >= 99 else max(60.0, total - elapsed)

    return {
        "percent": percent,
        "quality": quality,
        "quality_label": prior["quality_label"],
        "elapsed_seconds": int(round(elapsed)),
        "remaining_seconds": int(round(remaining)),
        "total_seconds": int(round(total)),
        "elapsed_label": format_duration(elapsed),
        "remaining_label": format_duration(remaining),
        "total_label": format_duration(total),
        "range_label": prior["range_label"],
        "note": prior["note"],
        "slow": slow,
    }
