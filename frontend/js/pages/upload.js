import { createJob, getHealth, listJobs } from "../api.js";
import { explainUploadError } from "../errors.js";
import { estimateQuality, jobTiming, videoDuration } from "../eta.js?v=4";
import { navigate } from "../router.js";

const IS_VIDEO = /\.(mov|mp4|m4v|mkv|webm|avi)$/i;
const IS_IMAGE = /\.(jpe?g|png|webp|tif|tiff|heic)$/i;

function mb(bytes) {
  return `${(bytes / 1e6).toFixed(bytes < 1e7 ? 2 : 0)} MB`;
}

export function renderUpload(root) {
  root.innerHTML = `
    <div class="page">
      <p class="home-label">Upload</p>
      <h1>Upload a video.</h1>
      <p class="lede">
        Fly a slow circle around the subject and keep it in the middle of the frame.
        Upload 1080p or 4K video, or photos from that orbit. Add the drone's flight log
        (SRT, CSV or GPX) if you want real-world measurements.
      </p>
      <p class="lede">
        Need a clip? <a href="#/watch/orbit">Watch the Ignatius sample</a> first.
        Ready-made 3D scenes are on
        <a href="#/examples">Examples</a> (Train, Truck, Room, Plush).
      </p>

      <div class="notice" id="blocked-note" hidden></div>
      <p class="notice queue-note" id="queue-note" hidden></p>

      <div id="upload-form">
        <div class="field">
          <label for="job-name">Job name</label>
          <input id="job-name" type="text" placeholder="e.g. Kitchen" autocomplete="off" />
        </div>

        <div class="quality-pick" role="radiogroup" aria-label="How much detail">
          <label class="quality-card">
            <input type="radio" name="quality" value="normal" checked />
            <strong>Normal</strong>
            <span>Faster. A full 3D model in colour. Good for a first look.</span>
            <em class="quality-eta" data-eta="normal">About 40–75 minutes</em>
          </label>
          <label class="quality-card">
            <input type="radio" name="quality" value="high" />
            <strong>Higher detail</strong>
            <span>Slower. Uses more of the video, and paints your own pictures onto the model when it can.</span>
            <em class="quality-eta" data-eta="high">About 2–4 hours</em>
          </label>
        </div>
        <p class="eta-pick" id="eta-pick">Normal usually takes 40–75 minutes on this computer.</p>

        <div class="drop" id="drop">
          <div class="drop-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" />
              <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
            </svg>
          </div>
          <p style="margin:0"><strong>Drop your video or photos here</strong></p>
          <p class="lede" style="margin:8px auto 0;font-size:0.92rem">
            mp4, mov, jpg, png · optional srt, csv, gpx · up to 4 GB
          </p>
          <input id="file-input" type="file" multiple accept="video/*,image/*,.srt,.csv,.gpx,.json" hidden />
          <div class="cover-acts" style="justify-content:center;margin:22px 0 0">
            <button class="act line" type="button" id="browse">Choose files</button>
          </div>
          <ul class="file-list" id="file-list"></ul>
        </div>

        <div class="send-bar" id="send-bar" hidden>
          <div class="bar"><span id="send-bar-fill" style="width:0%"></span></div>
          <p class="send-status" id="send-status">Sending…</p>
        </div>

        <div class="cover-acts">
          <button class="act fill" id="start" type="button">Build my 3D model</button>
          <a class="act line" href="#/jobs">View queue</a>
        </div>
      </div>
      <p class="error" id="upload-error"></p>
    </div>
  `;

  const files = new Map();
  const list = root.querySelector("#file-list");
  const drop = root.querySelector("#drop");
  const input = root.querySelector("#file-input");
  const sendBar = root.querySelector("#send-bar");
  const sendFill = root.querySelector("#send-bar-fill");
  const sendStatus = root.querySelector("#send-status");
  let catalog = null;
  let media = { durationSec: 0, photoCount: 0 };
  let blocked = false;
  let sending = false;

  function estimateFor(quality) {
    const key = quality === "high" ? "high" : "normal";
    return estimateQuality(key, {
      durationSec: media.durationSec,
      photoCount: media.photoCount,
      baseSeconds: catalog?.[key]?.seconds,
    });
  }

  function paintEta() {
    const normal = estimateFor("normal");
    const high = estimateFor("high");
    const normalEl = root.querySelector('[data-eta="normal"]');
    const highEl = root.querySelector('[data-eta="high"]');
    const pickEl = root.querySelector("#eta-pick");
    if (normalEl) normalEl.textContent = `About ${normal.rangeLabel}`;
    if (highEl) highEl.textContent = `About ${high.rangeLabel}`;
    const selected = root.querySelector('input[name="quality"]:checked')?.value || "normal";
    const pick = selected === "high" ? high : normal;
    const label = selected === "high" ? "Higher detail" : "Normal";
    const whose = media.durationSec || media.photoCount ? "This upload" : "A typical 3–5 minute orbit";
    if (pickEl) pickEl.textContent = `${whose}: about ${pick.rangeLabel} on this computer (${label}).`;
  }

  function blockUploads(title, detail) {
    blocked = true;
    const note = root.querySelector("#blocked-note");
    if (note) {
      note.hidden = false;
      note.innerHTML = `<span class="notice-body">
          <strong>${title}</strong>
          <span>${detail}</span>
          <span class="notice-acts">
            <a class="act line" href="#/examples">Open examples</a>
            <a class="act text" href="#/watch/orbit">Watch sample video</a>
          </span>
        </span>`;
    }
    const form = root.querySelector("#upload-form");
    if (form) form.hidden = true;
  }

  getHealth()
    .then((health) => {
      catalog = health.timing || null;
      paintEta();
      if (!health.colmap?.installed || !health.ffmpeg?.installed) {
        blockUploads(
          "This copy of the site cannot build 3D models.",
          "Building a model needs software that is not set up on this server. Open OnePass3D on the computer that runs it, or look at the ready-made scenes here."
        );
      }
    })
    .catch(() => paintEta());

  listJobs()
    .then((data) => {
      const busy = (data.jobs || []).filter((job) => job.status === "running" || job.status === "queued");
      const note = root.querySelector("#queue-note");
      if (!note || !busy.length || blocked) return;
      const running = busy.find((job) => job.status === "running");
      const wait = running ? jobTiming(running).remaining_label : null;
      const count = busy.length === 1 ? "1 job is" : `${busy.length} jobs are`;
      note.hidden = false;
      note.textContent = wait
        ? `${count} already in the queue. One computer builds one model at a time, so yours starts in about ${wait}.`
        : `${count} already in the queue. One computer builds one model at a time, so yours starts after that.`;
    })
    .catch(() => {});

  function refresh() {
    list.innerHTML = [...files.entries()]
      .map(
        ([key, file]) => `<li>
          <span>${file.name} · ${mb(file.size)}</span>
          <button type="button" class="file-drop" data-remove="${key}" aria-label="Remove ${file.name}">remove</button>
        </li>`
      )
      .join("");
  }

  async function recount() {
    media.photoCount = [...files.values()].filter((f) => IS_IMAGE.test(f.name)).length;
    const firstVideo = [...files.values()].find((f) => IS_VIDEO.test(f.name));
    media.durationSec = firstVideo ? await videoDuration(firstVideo) : 0;
    refresh();
    paintEta();
  }

  async function addFiles(fileList) {
    for (const file of fileList) files.set(file.name + file.size, file);
    await recount();
  }

  list.addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-remove]");
    if (!btn || sending) return;
    files.delete(btn.dataset.remove);
    await recount();
  });

  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("drag");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("drag");
    addFiles(e.dataTransfer.files);
  });
  root.querySelectorAll('input[name="quality"]').forEach((inputEl) => {
    inputEl.addEventListener("change", paintEta);
  });
  root.querySelector("#browse").addEventListener("click", () => input.click());
  input.addEventListener("change", () => addFiles(input.files));
  paintEta();

  root.querySelector("#start").addEventListener("click", async () => {
    const error = root.querySelector("#upload-error");
    error.textContent = "";
    if (blocked || sending) return;
    if (files.size === 0) {
      error.textContent = "Add a video or photos first.";
      return;
    }
    const button = root.querySelector("#start");
    sending = true;
    button.disabled = true;
    button.textContent = "Sending…";
    sendBar.hidden = false;
    sendFill.style.width = "0%";
    sendStatus.textContent = "Sending your files…";
    try {
      const quality = root.querySelector('input[name="quality"]:checked')?.value || "normal";
      const named = root.querySelector("#job-name").value.trim();
      const fallback = [...files.values()][0]?.name.replace(/\.[^.]+$/, "") || "Untitled";
      const job = await createJob(
        [...files.values()],
        named || fallback,
        quality,
        media.durationSec,
        (loaded, total, done) => {
          if (done) {
            sendFill.style.width = "100%";
            sendStatus.textContent = "Files sent. Starting the job…";
            return;
          }
          const pct = Math.min(99, Math.round((loaded / total) * 100));
          sendFill.style.width = `${pct}%`;
          sendStatus.textContent = `Sending your files… ${pct}% · ${mb(loaded)} of ${mb(total)}`;
        }
      );
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      sending = false;
      button.disabled = false;
      button.textContent = "Build my 3D model";
      sendBar.hidden = true;
      error.textContent = explainUploadError(err.message || err);
    }
  });
}
