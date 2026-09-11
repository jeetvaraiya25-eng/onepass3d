const REF_VIDEO_SECONDS = 240;
const REF_PHOTO_COUNT = 80;
const BASE = { normal: 55 * 60, high: 3 * 60 * 60 };

export function formatDuration(seconds) {
  const sec = Math.max(0, Math.round(Number(seconds) || 0));
  if (sec < 45) return "under a minute";
  const minutes = Math.round(sec / 60);
  if (minutes < 60) return minutes === 1 ? "1 minute" : `${minutes} minutes`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (rest === 0) return hours === 1 ? "1 hour" : `${hours} hours`;
  if (hours === 1) return `1 hr ${rest} min`;
  return `${hours} hr ${rest} min`;
}

export function formatRange(low, high) {
  const lowM = Math.max(1, Math.round(low / 60));
  const highM = Math.max(lowM + 1, Math.round(high / 60));
  if (highM < 90) return `${lowM}–${highM} minutes`;
  const lowH = Math.max(1, Math.round(low / 3600));
  const highH = Math.max(lowH + 1, Math.round(high / 3600));
  if (lowH === highH) return lowH === 1 ? "about 1 hour" : `about ${lowH} hours`;
  return `${lowH}–${highH} hours`;
}

function scaleForInput(durationSec, photoCount) {
  if (durationSec > 0) return Math.min(2.4, Math.max(0.5, durationSec / REF_VIDEO_SECONDS));
  if (photoCount > 0) return Math.min(2.4, Math.max(0.5, photoCount / REF_PHOTO_COUNT));
  return 1;
}

export function estimateQuality(quality, { durationSec = 0, photoCount = 0, baseSeconds } = {}) {
  const key = quality === "high" ? "high" : "normal";
  const mid = (baseSeconds || BASE[key]) * scaleForInput(durationSec, photoCount);
  const low = mid * 0.75;
  const high = mid * 1.35;
  return {
    quality: key,
    seconds: Math.round(mid),
    rangeLabel: formatRange(low, high),
  };
}

export function jobTiming(job) {
  const served = job?.timing;
  // an older backend can pin a long-running job at "any second now"; recompute in that case
  const trustServed =
    served?.remaining_label &&
    served.quality_label &&
    !(job.status === "running" && served.percent < 95 && Number(served.remaining_seconds) <= 60);
  if (trustServed) return served;
  const quality = job.quality === "high" ? "high" : "normal";
  const prior = estimateQuality(quality, { photoCount: Number(job.frame_count) || 0 });
  const status = job.status || "queued";
  let percent = Number(job.progress?.percent) || 0;
  if (status === "done") percent = 100;
  if (status === "failed") percent = 0;
  percent = Math.max(0, Math.min(100, percent));
  const started = Date.parse(job.started_at || job.created_at || "") || Date.now();
  let elapsed = Math.max(0, (Date.now() - started) / 1000);
  if (status === "queued") elapsed = 0;
  let total = prior.seconds;
  let slow = false;
  if (status === "running" && percent >= 12 && elapsed > 90) {
    const pace = elapsed / Math.max(percent / 100, 0.01);
    if (pace >= prior.seconds * 0.4 && pace <= prior.seconds * 2.2) {
      const w = Math.min(0.8, (percent - 12) / 45);
      total = prior.seconds * (1 - w) + pace * w;
    } else {
      total = Math.min(Math.max(pace, prior.seconds * 0.4), prior.seconds * 5);
      slow = pace > prior.seconds;
    }
  } else if (status === "running" && elapsed > prior.seconds) {
    total = elapsed * 1.5;
    slow = true;
  }
  let remaining = 0;
  if (status === "done") total = Math.max(elapsed, 1);
  else if (status !== "failed") {
    total = Math.max(elapsed + 60, total);
    remaining = percent >= 99 ? 0 : Math.max(60, total - elapsed);
  }
  const labels = { normal: "Normal", high: "Higher detail" };
  return {
    percent,
    quality,
    quality_label: labels[quality],
    elapsed_seconds: Math.round(elapsed),
    remaining_seconds: Math.round(remaining),
    total_seconds: Math.round(total),
    elapsed_label: formatDuration(elapsed),
    remaining_label: formatDuration(remaining),
    total_label: formatDuration(total),
    range_label: prior.rangeLabel,
    slow,
  };
}

export function videoDuration(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    const done = (value) => {
      URL.revokeObjectURL(url);
      resolve(value);
    };
    video.onloadedmetadata = () => done(Number.isFinite(video.duration) ? video.duration : 0);
    video.onerror = () => done(0);
    setTimeout(() => done(0), 4000);
    video.src = url;
  });
}
