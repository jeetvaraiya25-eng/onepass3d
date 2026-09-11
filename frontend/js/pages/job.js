import { cancelJob, deleteJob, fileUrl, getJob, listJobs, retryJob } from "../api.js";
import { escapeHtml, explainFailure } from "../errors.js";
import { jobTiming } from "../eta.js?v=4";

const STAGES = [
  { id: "queued", label: "Waiting to start", note: "Waiting for the computer to be free." },
  { id: "ingesting", label: "Reading your upload", note: "Reading the file you sent." },
  { id: "extracting", label: "Taking frames from the video", note: "Taking still pictures out of your video." },
  { id: "selecting", label: "Choosing the sharpest frames", note: "Keeping the sharp pictures and dropping the blurry ones." },
  { id: "features", label: "Finding landmarks", note: "Finding marks it can recognise again in every picture." },
  { id: "matching", label: "Matching the frames", note: "Working out which pictures show the same thing. This is usually the longest step." },
  { id: "cameras", label: "Working out the camera path", note: "Working out where the camera was for every picture." },
  { id: "validating_sparse", label: "Checking the camera path", note: "Checking the camera path makes sense." },
  { id: "undistorting", label: "Straightening the frames", note: "Straightening the pictures so they line up." },
  { id: "preparing_dense", label: "Getting ready to build", note: "Getting the pictures ready to build a surface." },
  { id: "dense", label: "Building the surface", note: "Filling in the surface of your subject. This step also takes a while." },
  { id: "fusion", label: "Cleaning up the surface", note: "Removing stray bits that do not belong." },
  { id: "meshing", label: "Shaping the model", note: "Turning the surface into a solid 3D shape." },
  { id: "refining", label: "Smoothing the model", note: "Smoothing the 3D shape." },
  { id: "texturing", label: "Adding the colours", note: "Painting your own pictures onto the 3D shape." },
  { id: "glb", label: "Packing the model", note: "Saving the finished model." },
  { id: "done", label: "Opening the model", note: "Opening your model." },
];

const GROUPS = [
  {
    id: "read",
    label: "Reading the video",
    still: "Still reading the video",
    stages: ["queued", "ingesting", "extracting", "selecting"],
  },
  {
    id: "match",
    label: "Matching the pictures",
    still: "Still matching the pictures",
    stages: ["features", "matching", "cameras", "validating_sparse"],
  },
  {
    id: "surface",
    label: "Building the surface",
    still: "Still building the surface",
    stages: ["undistorting", "preparing_dense", "dense", "fusion", "meshing"],
  },
  {
    id: "colour",
    label: "Colouring the model",
    still: "Still colouring the model",
    stages: ["refining", "texturing", "glb", "done"],
  },
];

const STAGE_INDEX = Object.fromEntries(STAGES.map((item, i) => [item.id, i]));
const GROUP_INDEX = Object.fromEntries(
  GROUPS.flatMap((group, i) => group.stages.map((id) => [id, i]))
);

function remainingCopy(job, timing) {
  const quality = timing.quality_label || "Normal";
  if (job.status === "queued") {
    return {
      title: `About ${timing.range_label} after it starts`,
      sub: `${quality} on this Mac`,
    };
  }
  if (timing.percent >= 99 || timing.remaining_seconds === 0) {
    return {
      title: "Finishing up",
      sub: `${timing.percent}% · ${timing.elapsed_label} in · ${quality}`,
    };
  }
  const slow = timing.slow ? " · slower than usual for this size" : "";
  return {
    title: `About ${timing.remaining_label} left`,
    sub: `${timing.percent}% · ${timing.elapsed_label} in · ${quality}${slow}`,
  };
}

function stageIndex(stage) {
  if (STAGE_INDEX[stage] != null) return STAGE_INDEX[stage];
  const aliases = {
    poses: "cameras",
    sparse: "validating_sparse",
    exporting: "glb",
    reconstructing: "features",
    simplifying: "refining",
    undistorting: "preparing_dense",
  };
  return STAGE_INDEX[aliases[stage] || "queued"] ?? 0;
}

const FILTERS = [
  { id: "all", label: "All" },
  { id: "active", label: "Working" },
  { id: "done", label: "Finished" },
  { id: "failed", label: "Stopped" },
];

function jobState(job) {
  if (job.status === "failed") return job.cancelled ? "cancelled" : "failed";
  return job.status;
}

function stateLabel(state) {
  if (state === "cancelled") return "cancelled";
  if (state === "running") return "working";
  return state;
}

function matchesFilter(job, filter) {
  const state = jobState(job);
  if (filter === "all") return true;
  if (filter === "active") return state === "running" || state === "queued";
  if (filter === "done") return state === "done";
  return state === "failed" || state === "cancelled";
}

function whenLabel(value) {
  const time = Date.parse(value || "");
  if (!time) return "";
  const date = new Date(time);
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  const clock = date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  if (sameDay) return `today ${clock}`;
  return `${date.toLocaleDateString(undefined, { day: "numeric", month: "short" })} · ${clock}`;
}

function jobRow(job) {
  const state = jobState(job);
  const href = `#/${state === "done" ? "view" : "jobs"}/${job.id}`;
  const points = job.point_count ? `${job.point_count.toLocaleString()} points` : "";
  const bits = [whenLabel(job.created_at), points].filter(Boolean).join(" · ");
  return `
    <li class="job-row" data-row="${job.id}">
      <a class="job-row-main" href="${href}">
        <span class="job-row-name">${escapeHtml(job.name)}</span>
        <span class="job-row-meta">${escapeHtml(bits)}</span>
      </a>
      <span class="badge ${state}">${stateLabel(state)}</span>
      <a class="open" href="${href}">Open →</a>
      <button type="button" class="job-del" data-del="${job.id}" aria-label="Delete ${escapeHtml(job.name)}">delete</button>
    </li>
  `;
}

export async function renderJobs(root) {
  root.innerHTML = `<div class="page"><p class="home-label">Queue</p><h1>Jobs.</h1><p class="lede">Loading…</p></div>`;
  let jobs = [];
  try {
    jobs = (await listJobs()).jobs || [];
  } catch {
    root.innerHTML = `
      <div class="page">
        <p class="home-label">Queue</p>
        <h1>Jobs.</h1>
        <p class="lede">Could not reach the server. Check that OnePass3D is running, then reload.</p>
      </div>`;
    return;
  }

  if (!jobs.length) {
    root.innerHTML = `
      <div class="page">
        <p class="home-label">Queue</p>
        <h1>Jobs.</h1>
        <p class="lede">Nothing here yet. Upload a video to build your first 3D model, or open a ready-made scene.</p>
        <div class="cover-acts">
          <a class="act fill" href="#/upload">Upload a video</a>
          <a class="act line" href="#/examples">Open examples</a>
        </div>
      </div>
    `;
    return;
  }

  let filter = "all";
  root.innerHTML = `
    <div class="page">
      <p class="home-label">Queue</p>
      <h1>Jobs.</h1>
      <p class="lede">Every model and example scene on this computer.</p>
      <div class="job-filters" id="job-filters" role="group" aria-label="Filter jobs">
        ${FILTERS.map(
          (item) =>
            `<button type="button" data-filter="${item.id}" class="${item.id === filter ? "is-on" : ""}">${item.label}</button>`
        ).join("")}
      </div>
      <ul class="job-rows" id="job-rows"></ul>
      <p class="job-count" id="job-count"></p>
    </div>
  `;

  const rows = root.querySelector("#job-rows");
  const count = root.querySelector("#job-count");

  function paintRows() {
    const shown = jobs.filter((job) => matchesFilter(job, filter));
    rows.innerHTML = shown.length
      ? shown.map(jobRow).join("")
      : `<li class="job-row is-empty">Nothing in this group.</li>`;
    count.textContent = `${shown.length} of ${jobs.length} ${jobs.length === 1 ? "job" : "jobs"}`;
  }
  paintRows();

  root.querySelector("#job-filters").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-filter]");
    if (!btn) return;
    filter = btn.dataset.filter;
    root.querySelectorAll("[data-filter]").forEach((el) => el.classList.toggle("is-on", el === btn));
    paintRows();
  });

  rows.addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-del]");
    if (!btn) return;
    const id = btn.dataset.del;
    const job = jobs.find((item) => item.id === id);
    const label = job ? job.name : id;
    if (job && (job.status === "running" || job.status === "queued")) {
      window.alert("This job is still working. Open it and press Cancel first.");
      return;
    }
    if (!window.confirm(`Delete "${label}"? The model and its files are removed from this computer.`)) return;
    btn.disabled = true;
    btn.textContent = "deleting…";
    try {
      await deleteJob(id);
      jobs = jobs.filter((item) => item.id !== id);
      paintRows();
    } catch {
      btn.disabled = false;
      btn.textContent = "delete";
    }
  });
}

function setText(el, value) {
  if (!el) return;
  const next = value == null ? "" : String(value);
  if (el.textContent !== next) el.textContent = next;
}

function patchKicker(root, job) {
  setText(root.querySelector("[data-job-id]"), job.status === "queued" ? "In the queue" : "Building");
}

function thumbNames(job) {
  if (Array.isArray(job.thumbs) && job.thumbs.length) return job.thumbs.slice(0, 8);
  if (Array.isArray(job.result?.thumbs) && job.result.thumbs.length) return job.result.thumbs.slice(0, 8);
  const stage = job.progress?.stage || job.status;
  if (stageIndex(stage) < (STAGE_INDEX.selecting ?? 3)) return [];
  return Array.from({ length: 8 }, (_, i) => `thumb_${String(i).padStart(2, "0")}.jpg`);
}

function groupsMarkup(job, view) {
  return GROUPS.map((group, i) => {
    const state = i < view.group ? "done" : i === view.group ? "now" : "";
    const extra =
      state === "now" && view.lede
        ? `<span class="step-note" data-note>${escapeHtml(view.lede)}</span>`
        : "";
    return `<li data-group="${group.id}" class="${state}">
      <span class="dot" aria-hidden="true"></span>
      <div class="step-copy">
        <strong>${group.label}</strong>
        ${extra}
      </div>
    </li>`;
  }).join("");
}

function viewModel(job, id, aheadLabel = "") {
  const cancelled = job.status === "failed" && Boolean(job.cancelled);
  const failed = job.status === "failed" && !cancelled;
  const percent = job.status === "failed" ? 100 : job.progress?.percent || 0;
  const stage = job.progress?.stage || job.status;
  const current = stageIndex(stage);
  const stageId = STAGES[current]?.id || "queued";
  const group = GROUP_INDEX[stageId] ?? 0;
  const thumbs = thumbNames(job).map(
    (name) => `<img src="${fileUrl(id, name)}" alt="" data-thumb />`
  );
  const fail = failed ? explainFailure(job.error || job.progress?.message) : null;
  const lede = failed
    ? "This did not finish. Here is what went wrong, in plain language."
    : cancelled
      ? "You stopped this job. Nothing was lost — the finished steps are saved and it can pick up from there."
      : job.status === "queued"
        ? aheadLabel || "Waiting for the computer to be free. It builds one model at a time."
        : STAGES[current]?.note || "";
  const running = job.status !== "failed" && job.status !== "done";
  const timing = jobTiming(job);
  const remain = remainingCopy(job, timing);
  const live =
    job.status === "queued"
      ? aheadLabel || "Waiting for the computer to be free."
      : timing.elapsed_label && timing.elapsed_label !== "under a minute"
        ? `${GROUPS[group].still} · ${timing.elapsed_label} in`
        : GROUPS[group].still;
  return { failed, cancelled, percent, current, group, thumbs, fail, lede, live, running, remain, timing };
}

function runningMarkup(job, view, cancelling = false) {
  const cancelLabel = cancelling ? "Cancelling…" : "Cancel";
  return `
    <div class="page">
      <p class="home-label" data-job-id>${job.status === "queued" ? "In the queue" : "Building"}</p>
      <h1 data-job-name>${escapeHtml(job.name)}</h1>
      <div class="eta-head">
        <div class="eta-row" aria-live="polite">
          <p class="eta-remain" data-eta-title>${escapeHtml(view.remain.title)}</p>
          <p class="eta-sub" data-eta-sub>${escapeHtml(view.remain.sub)}</p>
          <p class="eta-live" data-live-line>${escapeHtml(view.live)}</p>
          <p class="eta-warn" data-eta-warn hidden></p>
        </div>
        <div class="cover-acts eta-acts" data-acts>
          ${view.running ? `<button class="act line" type="button" id="cancel-job"${cancelling ? " disabled" : ""}>${cancelLabel}</button>` : ""}
          <a class="act text" href="#/jobs">All jobs</a>
        </div>
      </div>
      <div class="bar${view.running ? " is-live" : ""}"><span data-bar style="width:${view.percent}%"></span></div>
      <div class="thumbs" data-thumbs hidden>${view.thumbs.join("")}</div>
      <ul class="steps groups" data-groups>${groupsMarkup(job, view)}</ul>
    </div>
  `;
}

function cancelledMarkup(job, view) {
  return `
    <div class="page">
      <p class="home-label">Stopped</p>
      <h1>${escapeHtml(job.name)}</h1>
      <p class="lede">${escapeHtml(view.lede)}</p>
      <div class="stop-card">
        <p class="fail-kicker">Stopped by you</p>
        <h2>This job is not running any more.</h2>
        <p>Resume picks up from the last finished step, so you do not start from zero.</p>
        <div class="cover-acts">
          <button class="act fill" type="button" id="retry-job">Resume this job</button>
          <a class="act line" href="#/upload">Upload a different video</a>
        </div>
      </div>
      <div class="cover-acts">
        <a class="act text" href="#/jobs">All jobs</a>
      </div>
    </div>
  `;
}

function failMarkup(job, view) {
  const fail = view.fail;
  return `
    <div class="page">
      <p class="home-label">Did not finish</p>
      <h1>${escapeHtml(job.name)}</h1>
      <p class="lede">${escapeHtml(view.lede)}</p>
      <div class="fail-card">
        <p class="fail-kicker">What went wrong</p>
        <h2>${escapeHtml(fail.title)}</h2>
        <p>${escapeHtml(fail.detail)}</p>
        <p class="fail-next"><strong>What to do</strong> ${escapeHtml(fail.next)}</p>
        <div class="cover-acts">
          <button class="act fill" type="button" id="retry-job">Resume this job</button>
          <a class="act line" href="#/upload">Upload a new video</a>
        </div>
      </div>
      <div class="cover-acts">
        <a class="act text" href="#/jobs">All jobs</a>
      </div>
    </div>
  `;
}

function bindThumbErrors(root) {
  const wrap = root.querySelector("[data-thumbs]");
  if (!wrap) return;
  wrap.querySelectorAll("img").forEach((img) => {
    img.addEventListener("load", () => {
      wrap.hidden = false;
    });
    img.addEventListener("error", () => {
      img.remove();
    });
  });
}

function paintThumbs(root, view) {
  const thumbs = root.querySelector("[data-thumbs]");
  if (!thumbs) return;
  const html = view.thumbs.join("");
  const key = html;
  if (thumbs.dataset.key === key && !thumbs.hidden) return;
  thumbs.dataset.key = key;
  thumbs.innerHTML = html;
  if (!html) {
    thumbs.hidden = true;
    return;
  }
  bindThumbErrors(root);
}

function patchRunning(root, job, view, cancelling = false) {
  patchKicker(root, job);
  setText(root.querySelector("[data-job-name]"), job.name);
  setText(root.querySelector("[data-eta-title]"), view.remain.title);
  setText(root.querySelector("[data-eta-sub]"), view.remain.sub);
  setText(root.querySelector("[data-live-line]"), view.live);
  const warn = root.querySelector("[data-eta-warn]");
  if (warn && !warn.hidden) {
    warn.hidden = true;
    warn.textContent = "";
  }
  const bar = root.querySelector("[data-bar]");
  if (bar) bar.style.width = `${view.percent}%`;
  bar?.parentElement?.classList.toggle("is-live", view.running);
  const groups = root.querySelector("[data-groups]");
  if (groups) {
    const html = groupsMarkup(job, view);
    if (groups.innerHTML !== html) groups.innerHTML = html;
  }
  paintThumbs(root, view);
  const acts = root.querySelector("[data-acts]");
  if (acts && !cancelling) {
    const html = `${view.running ? `<button class="act line" type="button" id="cancel-job">Cancel</button>` : ""}
          <a class="act text" href="#/jobs">All jobs</a>`;
    if (acts.innerHTML.replace(/\s+/g, " ").trim() !== html.replace(/\s+/g, " ").trim()) {
      acts.innerHTML = html;
    }
  }
}

export async function renderJob(root, id) {
  let timer = null;
  let stopped = false;
  let mode = null;
  let cancelling = false;
  let misses = 0;
  let lastView = null;
  let aheadLabel = "";

  async function onRootClick(event) {
    const hit = event.target instanceof Element ? event.target : event.target?.parentElement;
    if (!hit) return;
    const retryBtn = hit.closest("#retry-job");
    if (retryBtn) {
      retryBtn.disabled = true;
      try {
        await retryJob(id);
        cancelling = false;
        clearTimeout(timer);
        timer = setTimeout(paint, 400);
      } catch {
        retryBtn.disabled = false;
      }
      return;
    }
    const cancelBtn = hit.closest("#cancel-job");
    if (cancelBtn && !cancelling) {
      const spent = lastView?.remain?.sub ? ` You are ${lastView.timing.elapsed_label} in.` : "";
      if (!window.confirm(`Stop building this model?${spent} You can resume it later from the last finished stage.`)) {
        return;
      }
      cancelling = true;
      cancelBtn.disabled = true;
      cancelBtn.textContent = "Cancelling…";
      try {
        await cancelJob(id);
        clearTimeout(timer);
        await paint();
      } catch {
        cancelling = false;
        cancelBtn.disabled = false;
        cancelBtn.textContent = "Cancel";
      }
    }
  }

  root.addEventListener("click", onRootClick);

  function showOffline() {
    const warn = root.querySelector("[data-eta-warn]");
    if (warn) {
      warn.hidden = false;
      warn.textContent =
        misses < 6
          ? "Lost touch with the server for a moment — still trying."
          : "Cannot reach OnePass3D. The job keeps running; this page will catch up when the server answers.";
      return;
    }
    if (mode === null) {
      root.innerHTML = `
        <div class="page">
          <p class="home-label">Offline</p>
          <h1>Cannot reach the server.</h1>
          <p class="lede">Check that OnePass3D is running, then reload this page.</p>
          <div class="cover-acts"><a class="act text" href="#/jobs">All jobs</a></div>
        </div>`;
    }
  }

  async function queueAhead(job) {
    if (job.status !== "queued") return "";
    try {
      const data = await listJobs();
      const running = (data.jobs || []).find((item) => item.status === "running" && item.id !== id);
      if (!running) return "";
      const wait = jobTiming(running).remaining_label;
      return `Waiting for "${running.name}" to finish, about ${wait}. This computer builds one model at a time.`;
    } catch {
      return "";
    }
  }

  async function paint() {
    if (stopped) return;
    let job;
    try {
      job = await getJob(id);
    } catch {
      misses += 1;
      showOffline();
      if (!stopped) {
        clearTimeout(timer);
        timer = setTimeout(paint, Math.min(8000, 1200 * misses));
      }
      return;
    }
    if (stopped) return;
    misses = 0;
    if (job.status === "done") {
      window.location.hash = `/view/${job.id}`;
      return;
    }
    if (job.status === "queued" && !aheadLabel) aheadLabel = await queueAhead(job);
    if (job.status !== "queued") aheadLabel = "";
    const view = viewModel(job, id, aheadLabel);
    lastView = view;
    if (view.failed || view.cancelled) cancelling = false;
    const nextMode = view.failed ? "fail" : view.cancelled ? "stopped" : "run";
    if (mode !== nextMode) {
      root.innerHTML =
        nextMode === "fail"
          ? failMarkup(job, view)
          : nextMode === "stopped"
            ? cancelledMarkup(job, view)
            : runningMarkup(job, view, cancelling);
      mode = nextMode;
      if (nextMode === "run") paintThumbs(root, view);
    } else if (nextMode === "run") {
      patchRunning(root, job, view, cancelling);
    }
    if (job.status !== "failed") {
      clearTimeout(timer);
      timer = setTimeout(paint, 1200);
    }
  }

  await paint();
  return () => {
    stopped = true;
    clearTimeout(timer);
    root.removeEventListener("click", onRootClick);
  };
}
