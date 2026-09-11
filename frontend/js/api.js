const API = "/api";

async function parseError(res) {
  try {
    const data = await res.json();
    return data.detail || data.message || res.statusText;
  } catch {
    return res.statusText;
  }
}

export function createJob(files, name, quality = "normal", durationSec = 0, onProgress) {
  const body = new FormData();
  body.append("name", name || "Untitled");
  body.append("quality", quality === "high" ? "high" : "normal");
  if (durationSec > 0) body.append("duration_sec", String(Math.round(durationSec)));
  for (const file of files) body.append("files", file);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API}/jobs`);
    if (onProgress) {
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) onProgress(event.loaded, event.total);
      });
      xhr.upload.addEventListener("load", () => onProgress(1, 1, true));
    }
    xhr.addEventListener("load", () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* server sent something that is not JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300 && data) resolve(data);
      else reject(new Error(data?.detail || data?.message || xhr.statusText || `HTTP ${xhr.status}`));
    });
    xhr.addEventListener("error", () => reject(new Error("The connection dropped while uploading.")));
    xhr.addEventListener("timeout", () => reject(new Error("The upload timed out.")));
    xhr.send(body);
  });
}

export async function createDemo(scene = "train") {
  const res = await fetch(`${API}/jobs/demo?scene=${encodeURIComponent(scene)}`, { method: "POST" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listExamples() {
  const res = await fetch(`${API}/examples`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getJob(id) {
  const res = await fetch(`${API}/jobs/${id}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function listJobs() {
  const res = await fetch(`${API}/jobs`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function deleteJob(jobId) {
  const res = await fetch(`${API}/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export function fileUrl(jobId, filename) {
  return `${API}/jobs/${jobId}/files/${encodeURIComponent(filename)}`;
}

export async function getHealth() {
  const res = await fetch(`${API}/health`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function retryJob(jobId) {
  const res = await fetch(`${API}/reconstruction/${jobId}/retry`, { method: "POST" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function cancelJob(jobId) {
  const res = await fetch(`${API}/reconstruction/${jobId}/cancel`, { method: "POST" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
