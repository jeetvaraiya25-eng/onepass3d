const API = "/api";

async function parseError(res) {
  try {
    const data = await res.json();
    return data.detail || data.message || res.statusText;
  } catch {
    return res.statusText;
  }
}

export async function createJob(files, name, quality = "normal") {
  const body = new FormData();
  body.append("name", name || "Untitled flight");
  body.append("quality", quality === "high" ? "high" : "normal");
  for (const file of files) body.append("files", file);
  const res = await fetch(`${API}/jobs`, { method: "POST", body });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
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
