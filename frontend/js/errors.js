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

// names of the tools and files behind the scenes: never show these to someone using the site
function namesInternals(text) {
  return /colmap|openmvs|patchmatch|cuda|ffmpeg|gaussian|3dgs|splat|sfm|mvs\b|\.ply|\.mvs|\.glb|\.obj|dense|sparse|mesh|densify|decimat|uvicorn|brew |python |tools\/|--[a-z-]+/i.test(
    text
  );
}

function safeDetail(text, fallback) {
  return text && !looksTechnical(text) && !namesInternals(text) ? text : fallback;
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
        "The pictures were mixed — some upright, some sideways, or different sizes. It stopped while trying to follow the same spots from one picture to the next.",
      next: "Upload again, holding the camera the same way for every shot and moving so each picture overlaps the last.",
    };
  }

  if (looksTechnical(text)) {
    return {
      title: "Building the model stopped",
      detail:
        "The pictures could not be followed all the way through. That is about the pictures themselves, not your account.",
      next: "Upload again with a slower circle, or more overlapping photos of the same place, all held the same way.",
    };
  }

  if (text === "'list'" || text === "list" || /could not read the openmvs file/.test(lower)) {
    return {
      title: "It stopped while saving the surface",
      detail:
        "The camera path and the surface were worked out, then the app hit a problem reading one of its own files.",
      next: "Press Resume this job. It carries on from the surface, so your video is not uploaded again.",
    };
  }

  if (/openmvs is not installed|colmap is not installed|patchmatch|cuda gpu/.test(lower)) {
    return {
      title: "This computer is not set up to build models",
      detail:
        "Part of the software that builds the 3D model is missing on the computer running OnePass3D.",
      next: "Open OnePass3D on the computer that is set up for it, then upload again.",
    };
  }

  if (/failed quality validation/.test(lower)) {
    return {
      title: "The model came out too broken to show",
      detail: "Too much of the subject was missing or in pieces to call it a finished model.",
      next: "Fly a slower circle with more overlap between one moment and the next, then upload again.",
    };
  }

  if (/cancelled/.test(lower)) {
    return {
      title: "You stopped this job",
      detail: "It was stopped before the model was finished.",
      next: "Press Resume this job to carry on, or upload a new video.",
    };
  }

  if (/mac slept|app stopped/.test(lower)) {
    return {
      title: "This job paused when the computer stopped",
      detail:
        "Your earlier models are still saved. This run did not finish because the computer went to sleep or the app was closed.",
      next: "Press Resume this job. Some steps may start over.",
    };
  }

  if (/insufficient camera registration|were registered/.test(lower)) {
    return {
      title: "It could not follow the camera",
      detail: "Too few moments in the video could be lined up with each other.",
      next: "Move the camera more slowly so each moment overlaps the last, then upload again.",
    };
  }

  if (/disconnected reconstruction components/.test(lower)) {
    return {
      title: "The camera path broke apart",
      detail: "The video jumped between views that share nothing, so it became two separate pieces.",
      next: "Keep the camera moving smoothly around one subject, without cutting to a different spot.",
    };
  }

  if (/need at least/.test(lower) && /frame/.test(lower)) {
    return {
      title: "Not enough clear pictures",
      detail: safeDetail(text, "There were too few sharp pictures of the subject to work with."),
      next: "Upload a longer clip of one slow circle, or at least five sharp photos that overlap.",
    };
  }

  if (/too blurry/.test(lower)) {
    return {
      title: "The video is too blurry",
      detail: safeDetail(text, "Almost every moment in the video was blurred by movement."),
      next: "Fly slower and keep the subject in the middle of the frame. A fast cinematic pass will not work.",
    };
  }

  if (/same viewpoint|barely moved/.test(lower)) {
    return {
      title: "The camera barely moved",
      detail: safeDetail(text, "Every picture was taken from nearly the same spot, so there is no second angle to work from."),
      next: "Fly a slow circle so each second shows a new angle, then upload again.",
    };
  }

  if (/no visual features|blank sky/.test(lower)) {
    return {
      title: "There was nothing to lock on to",
      detail: safeDetail(text, "Most of the frame was plain sky, water or blank wall."),
      next: "Point the camera at buildings, ground or objects with visible detail.",
    };
  }

  if (/too thin to form a surface/.test(lower)) {
    return {
      title: "A solid surface could not be formed",
      detail: safeDetail(text, "The subject was only seen from one side, so there was not enough to close up into a shape."),
      next: "Circle all the way around so walls and ground are seen from several sides.",
    };
  }

  if (/not enough 3d points|not enough overlapping/.test(lower)) {
    return {
      title: "Not enough of the subject was visible",
      detail: "The pictures did not overlap enough, or they were too blurry, for a 3D model to form.",
      next: "Fly a slower circle around the subject, or take more overlapping photos of the same place.",
    };
  }

  if (/could not open video|no readable frames/.test(lower)) {
    return {
      title: "The video could not be read",
      detail: "The file was missing pictures, or it is not a format this site can open.",
      next: "Save the clip as MP4 and upload again. A short cinematic fly-by will also fail — use a slow circle.",
    };
  }

  if (/exceeds 600 mb|exceeds 4 gb/.test(lower)) {
    return {
      title: "This file is too large",
      detail: "4K videos are often over a gigabyte. Uploads can be up to 4 GB.",
      next: "Save a 1080p copy of the clip and upload that instead.",
    };
  }

  if (/none of the uploaded photos/.test(lower)) {
    return {
      title: "The photos could not be opened",
      detail: "The files were not readable pictures, or they were damaged on the way up.",
      next: "Upload JPG or PNG photos and try again.",
    };
  }

  return {
    title: "Building the model stopped",
    detail: safeDetail(text, "Something in the upload stopped it before a model could be made."),
    next: "Upload again with a slow circle, or at least five overlapping photos of the same place.",
  };
}

export function explainUploadError(raw) {
  const text = asText(raw);
  const fallback = "The upload could not be started. Use a video (MP4 or MOV) or photos (JPG or PNG), then try again.";
  return safeDetail(text, fallback);
}
