import { cancelJob, fileUrl, getJob, listJobs, retryJob } from "../api.js";
import { escapeHtml, explainFailure, publicLogs } from "../errors.js";

const STAGES = [
  { id: "queued", label: "Queued" },
  { id: "ingesting", label: "Uploading" },
  { id: "extracting", label: "Extracting frames" },
  { id: "selecting", label: "Selecting frames" },
  { id: "features", label: "Extracting features" },
  { id: "matching", label: "Matching images" },
  { id: "cameras", label: "Reconstructing cameras" },
  { id: "validating_sparse", label: "Validating sparse model" },
  { id: "undistorting", label: "Undistorting images" },
  { id: "preparing_dense", label: "Preparing dense reconstruction" },
  { id: "dense", label: "Dense reconstruction" },
  { id: "fusion", label: "Fusing / filtering points" },
  { id: "meshing", label: "Generating mesh" },
  { id: "refining", label: "Refining mesh" },
  { id: "texturing", label: "Texturing" },
  { id: "glb", label: "Creating GLB" },
  { id: "done", label: "Loading 3D model" },
];

const STAGE_INDEX = Object.fromEntries(STAGES.map((item, i) => [item.id, i]));

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

export async function renderJobs(root) {
  root.innerHTML = `<p class="chip">Queue</p><h1>Jobs</h1><p class="lede">Loading…</p>`;
  const data = await listJobs();
  if (!data.jobs.length) {
    root.innerHTML = `
      <p class="chip">Queue</p>
      <h1>Jobs</h1>
      <div class="empty" style="margin-top:30px">
        <p>Nothing processed yet. Start with a photoreal example or upload a flight.</p>
        <div class="actions" style="justify-content:center;margin:0">
          <a class="btn primary" href="#/examples">Open an example</a>
          <a class="btn ghost" href="#/upload">New flight</a>
        </div>
      </div>
    `;
    return;
  }
  root.innerHTML = `
    <p class="chip">Queue</p>
    <h1>Jobs</h1>
    <p class="lede">Every reconstruction and example scene you have opened on this machine.</p>
    <div class="table-wrap" style="margin-top:30px">
      <table class="job-table">
        <thead><tr><th>Name</th><th>Status</th><th>Points</th><th>GPS</th><th></th></tr></thead>
        <tbody>
          ${data.jobs
            .map(
              (job) => `
            <tr>
              <td>${job.name}</td>
              <td><span class="badge ${job.status}">${job.status}</span></td>
              <td class="num">${job.point_count ? job.point_count.toLocaleString() : "—"}</td>
              <td class="num">${job.has_gps ? "locked" : "none"}</td>
              <td><a class="open" href="#/${job.status === "done" ? "view" : "jobs"}/${job.id}">Open →</a></td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

export async function renderJob(root, id) {
  let timer = null;
  async function paint() {
    const job = await getJob(id);
    const failed = job.status === "failed";
    const percent = failed ? 100 : job.progress?.percent || 0;
    const stage = job.progress?.stage || job.status;
    const current = stageIndex(stage);
    const thumbs = (job.result?.thumbs || []).map(
      (name) => `<img src="${fileUrl(id, name)}" alt="keyframe" />`
    );
    const fail = failed ? explainFailure(job.error || job.progress?.message) : null;
    const lede = failed
      ? "This reconstruction did not finish. Here is what went wrong, in plain language."
      : job.status === "queued"
        ? "Waiting behind another job. Photoreal examples no longer wait — open Examples again if this stays here."
        : job.progress?.message || "";
    const logs = publicLogs(job.logs);
    const running = !failed && job.status !== "done";
    root.innerHTML = `
      <p class="chip">Job ${escapeHtml(job.id)}</p>
      <h1>${escapeHtml(job.name)}</h1>
      <p class="lede">${escapeHtml(lede)}</p>
      ${
        fail
          ? `<div class="fail-card">
              <p class="fail-kicker">What went wrong</p>
              <h2>${escapeHtml(fail.title)}</h2>
              <p>${escapeHtml(fail.detail)}</p>
              <p class="fail-next"><strong>What to do</strong> ${escapeHtml(fail.next)}</p>
              <div class="actions">
                <button class="btn primary" type="button" id="retry-job">Resume this job</button>
                <a class="btn ghost" href="#/upload">Start a new reconstruction</a>
              </div>
            </div>`
          : `<div class="bar"><span style="width:${percent}%"></span></div>
      <ul class="steps">
        ${STAGES.map(
          (item, i) => `<li class="${i <= current || job.status === "done" ? "on" : ""}">
            <span class="dot"></span>${item.label}
          </li>`
        ).join("")}
      </ul>`
      }
      ${thumbs.length ? `<div class="thumbs">${thumbs.join("")}</div>` : ""}
      ${!failed && logs.length ? `<pre class="logs">${escapeHtml(logs.join("\n"))}</pre>` : ""}
      <div class="actions">
        ${job.status === "done" ? `<a class="btn primary" href="#/view/${job.id}">Open 3D viewer</a>` : ""}
        ${running ? `<button class="btn ghost" type="button" id="cancel-job">Cancel</button>` : ""}
        <a class="btn ghost" href="#/jobs">All jobs</a>
      </div>
    `;
    const retryBtn = root.querySelector("#retry-job");
    if (retryBtn) {
      retryBtn.addEventListener("click", async () => {
        retryBtn.disabled = true;
        try {
          await retryJob(id);
          timer = setTimeout(paint, 400);
        } catch {
          retryBtn.disabled = false;
        }
      });
    }
    const cancelBtn = root.querySelector("#cancel-job");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", async () => {
        cancelBtn.disabled = true;
        try {
          await cancelJob(id);
        } catch {
          cancelBtn.disabled = false;
        }
      });
    }
    if (job.status === "done") {
      window.location.hash = `/view/${job.id}`;
      return;
    }
    if (job.status !== "failed") {
      timer = setTimeout(paint, 1200);
    }
  }
  await paint();
  return () => clearTimeout(timer);
}
