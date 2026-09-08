export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function asText(raw) {
  if (raw == null) return "";
  if (typeof raw === "string") return raw.trim();
  if (Array.isArray(raw)) {
    return raw
      .map((item) => (item && item.msg) || (typeof item === "string" ? item : ""))
      .filter(Boolean)
      .join(" ");
  }
  if (typeof raw === "object") {
    return String(raw.detail || raw.message || raw.msg || "").trim();
  }
  return String(raw).trim();
}

function looksTechnical(text) {
  return /opencv|\.cpp:|assertion failed|traceback|lkpyramid|prevpyr|cv2\.|file \".+:\d+|error: \(-\d+\)/i.test(
    text
  );
}

export function explainFailure(raw) {
  const text = asText(raw);
  const lower = text.toLowerCase();

  if (
    /lkpyramid|prevpyr|lvlstep/.test(lower) ||
    (/opencv/.test(lower) && /size\(\)|assertion/.test(lower))
  ) {
    return {
      title: "These photos didn’t line up",
      detail:
        "The pictures were mixed — some upright, some sideways, or different sizes. The rebuild stopped while trying to follow the same spots from one photo to the next.",
      next: "Start a new job. Hold the phone the same way for every shot, walk around so each photo overlaps the last, and upload again. Reopening this failed job will not retry it.",
    };
  }

  if (looksTechnical(text)) {
    return {
      title: "The 3D rebuild stopped",
      detail:
        "The photos or video could not be tracked all the way through. That is a matching problem in the pictures, not a problem with your account.",
      next: "Start a new job with a slower pass, or more overlapping photos of the same place, all taken in the same orientation.",
    };
  }

  if (/need at least/.test(lower) && /frame/.test(lower)) {
    return {
      title: "Not enough clear frames",
      detail: text,
      next: "Upload a longer single-pass clip, or at least five sharp photos that overlap and show the same area.",
    };
  }

  if (/not enough 3d points/.test(lower)) {
    return {
      title: "Not enough of the scene was visible",
      detail:
        "The photos did not overlap enough, or they were too blurry, for a 3D model to form.",
      next: "Fly a slower circle around the subject, or take more than five overlapping photos of the same place, then start a new job.",
    };
  }

  if (/could not open video|no readable frames/.test(lower)) {
    return {
      title: "The video could not be read",
      detail: "The file was missing frames, or it is not a format this site can open.",
      next: "Export the clip as MP4 (H.264) and start a new job. A short cinematic fly-by with motion blur will also fail — use a slow orbit.",
    };
  }

  if (/exceeds 600 mb|exceeds 4 gb/.test(lower)) {
    return {
      title: "This file is too large",
      detail: "4K videos are often over a gigabyte. This site now accepts uploads up to 4 GB.",
      next: "If the file is still larger than 4 GB, export a 1080p copy from Photos and start a new job.",
    };
  }

  if (/none of the uploaded photos/.test(lower)) {
    return {
      title: "The photos could not be opened",
      detail: "The files were not readable stills, or they were damaged in transfer.",
      next: "Upload JPG or PNG photos and start a new job.",
    };
  }

  if (text) {
    return {
      title: "Reconstruction stopped",
      detail: text,
      next: "Start a new job with a cleaner orbit or more overlapping photos. This failed job will not retry.",
    };
  }

  return {
    title: "Reconstruction didn’t finish",
    detail: "Something in the upload stopped the 3D rebuild before a model could be made.",
    next: "Start a new job. Use a slow orbit or at least five overlapping photos of the same place, all in the same orientation.",
  };
}

export function explainUploadError(raw) {
  const text = asText(raw);
  if (!text) return "The upload could not be started. Add a video or photos, then try again.";
  if (looksTechnical(text)) {
    return "The upload could not be started. Use a video (MP4 or MOV) or photos (JPG or PNG), then try again.";
  }
  return text;
}

export function publicLogs(logs) {
  return (logs || []).map((line) => String(line || "").trim()).filter((line) => line && !looksTechnical(line) && !/^failed:/i.test(line));
}
