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

  if (text === "'list'" || text === "list" || /could not read the openmvs file/.test(lower)) {
    return {
      title: "A file-format bug stopped the mesh step",
      detail:
        "Camera tracking and the dense point cloud finished. The app then failed while reading the OpenMVS point file.",
      next: "Click Resume this job. It should continue from the dense point cloud, not from the 3 GB upload.",
    };
  }

  if (/openmvs is not installed/.test(lower)) {
    return {
      title: "OpenMVS is not installed on this machine.",
      detail:
        "This Mac cannot run COLMAP PatchMatch without CUDA. OpenMVS is the local dense reconstruction engine.",
      next: "Put the official OpenMVS macOS arm64 binaries in tools/openmvs, or set OPENMVS_PATH, then start a new job.",
    };
  }

  if (/failed quality validation/.test(lower)) {
    return {
      title: "Reconstruction failed quality validation",
      detail: text,
      next: "The model was too fragmented or incomplete to show as a finished 3D result. Film a slower pass with more overlap.",
    };
  }

  if (/colmap is not installed/.test(lower)) {
    return {
      title: "COLMAP is not installed on this machine.",
      detail:
        "OnePass3D now uses COLMAP for photogrammetry. Install it on this computer, then start a new job.",
      next: "On macOS run: brew install colmap. Then restart the backend with python run.py.",
    };
  }

  if (/cancelled/.test(lower)) {
    return {
      title: "Reconstruction was cancelled",
      detail: "The COLMAP process was stopped before a model was written.",
      next: "Start a new job if you want to try again.",
    };
  }

  if (/mac slept|app stopped/.test(lower)) {
    return {
      title: "This job paused when the Mac stopped",
      detail:
        "The first Ignatius model is still saved. This higher-detail run did not finish because the computer went to sleep or the app was closed.",
      next: "Start the local server again, then click Resume this job. Matching may start over.",
    };
  }

  if (/insufficient camera registration|were registered/.test(lower)) {
    return {
      title: "Insufficient camera registration",
      detail: text,
      next: "Move the camera more slowly so consecutive frames overlap, then start a new job.",
    };
  }

  if (/disconnected reconstruction components/.test(lower)) {
    return {
      title: "The camera trajectory broke apart",
      detail: text,
      next: "Keep the camera moving continuously through the same space. Do not jump to unrelated viewpoints.",
    };
  }

  if (/patchmatch|cuda gpu/.test(lower)) {
    return {
      title: "Dense reconstruction needs a CUDA GPU",
      detail: text,
      next: "Feature matching and camera poses can run on this Mac in CPU mode. PatchMatch MVS needs NVIDIA CUDA, or a machine with RECON_WORKER_URL set.",
    };
  }

  if (/need at least/.test(lower) && /frame/.test(lower)) {
    return {
      title: "Not enough clear frames",
      detail: text,
      next: "Upload a longer single-pass clip, or at least five sharp photos that overlap and show the same area.",
    };
  }

  if (/too blurry/.test(lower)) {
    return {
      title: "The video is too blurry",
      detail: text,
      next: "Fly slower, keep the subject in frame, and start a new job. A fast cinematic pass will not reconstruct.",
    };
  }

  if (/same viewpoint|barely moved/.test(lower)) {
    return {
      title: "The camera barely moved",
      detail: text,
      next: "Fly a slow orbit or a straight pass so each second shows a new angle. Then start a new job.",
    };
  }

  if (/no visual features|blank sky/.test(lower)) {
    return {
      title: "Not enough texture in the scene",
      detail: text,
      next: "Point the camera at buildings, roads, or ground with detail — not empty sky or water.",
    };
  }

  if (/too thin to form a surface/.test(lower)) {
    return {
      title: "A surface could not be formed",
      detail: text,
      next: "Orbit so walls and ground are seen from several sides. Reopening this job will not retry it.",
    };
  }

  if (/not enough 3d points|not enough overlapping/.test(lower)) {
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
