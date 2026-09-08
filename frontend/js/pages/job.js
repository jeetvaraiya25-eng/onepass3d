import { fileUrl, getJob, listJobs } from "../api.js";
import { escapeHtml, explainFailure, publicLogs } from "../errors.js";

const STAGES = ["queued", "ingesting", "reconstructing", "georeferencing", "exporting", "done"];

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
                <a class="btn primary" href="#/upload">Start a new reconstruction</a>
                <a class="btn ghost" href="#/examples">Open a photoreal example</a>
              </div>
            </div>`
          : `<div class="bar"><span style="width:${percent}%"></span></div>
      <ul class="steps">
        ${STAGES.map(
          (name) => `<li class="${STAGES.indexOf(stage) >= STAGES.indexOf(name) || job.status === "done" ? "on" : ""}">
            <span class="dot"></span>${name}
          </li>`
        ).join("")}
      </ul>`
      }
      ${thumbs.length ? `<div class="thumbs">${thumbs.join("")}</div>` : ""}
      ${!failed && logs.length ? `<pre class="logs">${escapeHtml(logs.join("\n"))}</pre>` : ""}
      <div class="actions">
        ${job.status === "done" ? `<a class="btn primary" href="#/view/${job.id}">Open 3D viewer</a>` : ""}
        <a class="btn ghost" href="#/jobs">All jobs</a>
      </div>
    `;
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
