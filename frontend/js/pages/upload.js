import { createJob, getHealth } from "../api.js";
import { explainUploadError } from "../errors.js";
import { navigate } from "../router.js";

export function renderUpload(root) {
  root.innerHTML = `
    <p class="chip">New reconstruction</p>
    <h1>Upload a video</h1>
    <p class="lede">
      Fly a slow Point of Interest circle around the site, keep the subject in frame,
      and upload 1080p/4K video or stills. Add a DJI SRT, CSV, or GPX file for metric
      GPS lock. A one-way cinematic pass will leave most facades empty.
    </p>
    <p class="lede" style="font-size:0.95rem">
      Need a clip? <a href="#/watch/orbit">Watch the sample chimney orbit</a> and download
      it there, or study the
      <a href="https://www.youtube.com/shorts/ZV2BgGGax1s" target="_blank" rel="noreferrer">DJI Mini 4 Pro orbit short</a>
      for the flight pattern. Photoreal 3D lives on
      <a href="#/examples">Train / Truck / Room / Plush</a>, not this upload.
    </p>

    <div class="field">
      <label for="job-name">Job name</label>
      <input id="job-name" value="Kitchen scan" />
    </div>

    <div class="quality-pick" role="radiogroup" aria-label="Reconstruction quality">
      <label class="quality-card">
        <input type="radio" name="quality" value="normal" checked />
        <strong>Normal</strong>
        <span>Faster. FINAL is a colored 3D mesh from the dense cloud. Use this for a first look.</span>
      </label>
      <label class="quality-card">
        <input type="radio" name="quality" value="high" />
        <strong>Higher detail</strong>
        <span>Slower. More frames and a photo texture when the video has enough overlap.</span>
      </label>
    </div>

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
      <div class="actions" style="justify-content:center;margin:22px 0 0">
        <button class="btn ghost" type="button" id="browse">Choose files</button>
      </div>
      <ul class="file-list" id="file-list"></ul>
    </div>

    <div class="actions">
      <button class="btn primary" id="start" type="button">Start reconstruction</button>
      <a class="btn ghost" href="#/jobs">View queue</a>
    </div>
    <p class="error" id="upload-error"></p>
    <p class="lede" id="colmap-status" style="margin-top:18px;font-size:0.92rem"></p>
  `;

  getHealth()
    .then((health) => {
      const el = root.querySelector("#colmap-status");
      if (!el) return;
      if (!health.colmap?.installed) {
        el.textContent = "COLMAP is not installed on this machine. Install it with brew install colmap, then restart the backend.";
        return;
      }
      if (!health.openmvs?.installed && health.denseBackend === "unavailable") {
        el.textContent = "COLMAP is installed, but this Mac cannot finish a 3D mesh without OpenMVS. Place OpenMVS binaries in tools/openmvs.";
        return;
      }
      el.textContent = health.openmvs?.installed
        ? "Local Mac pipeline: COLMAP cameras + OpenMVS dense mesh. No CUDA required."
        : "COLMAP is installed. Dense reconstruction will use OpenMVS if PatchMatch cannot run.";
    })
    .catch(() => {});

  const files = new Map();
  const list = root.querySelector("#file-list");
  const drop = root.querySelector("#drop");
  const input = root.querySelector("#file-input");

  function refresh() {
    list.innerHTML = [...files.values()].map((f) => `<li>${f.name} · ${(f.size / 1e6).toFixed(2)} MB</li>`).join("");
  }

  function addFiles(fileList) {
    for (const file of fileList) files.set(file.name + file.size, file);
    const nameInput = root.querySelector("#job-name");
    const firstVideo = [...files.values()].find((f) => /\.(mov|mp4|m4v|mkv|webm|avi)$/i.test(f.name));
    if (firstVideo && (nameInput.value === "Kitchen scan" || nameInput.value === "Orbit flight")) {
      nameInput.value = firstVideo.name.replace(/\.[^.]+$/, "");
    }
    refresh();
  }

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
  root.querySelector("#browse").addEventListener("click", () => input.click());
  input.addEventListener("change", () => addFiles(input.files));

  root.querySelector("#start").addEventListener("click", async () => {
    const error = root.querySelector("#upload-error");
    error.textContent = "";
    if (files.size === 0) {
      error.textContent = "Add a video or photos first.";
      return;
    }
    const button = root.querySelector("#start");
    button.disabled = true;
    button.textContent = "Uploading…";
    try {
      const quality = root.querySelector('input[name="quality"]:checked')?.value || "normal";
      const job = await createJob([...files.values()], root.querySelector("#job-name").value, quality);
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      button.disabled = false;
      button.textContent = "Start reconstruction";
      error.textContent = explainUploadError(err.message || err);
    }
  });
}
