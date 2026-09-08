export function route() {
  const hash = window.location.hash.replace(/^#/, "") || "/";
  const parts = hash.split("/").filter(Boolean);
  if (parts.length === 0) return { name: "home" };
  if (parts[0] === "upload") return { name: "upload" };
  if (parts[0] === "examples") return { name: "examples" };
  if (parts[0] === "watch") return { name: "watch", id: parts[1] || "orbit" };
  if (parts[0] === "jobs" && parts[1]) return { name: "job", id: parts[1] };
  if (parts[0] === "jobs") return { name: "jobs" };
  if (parts[0] === "view" && parts[1] === "example" && parts[2]) {
    return { name: "example-view", scene: parts[2] };
  }
  if (parts[0] === "view" && parts[1]) return { name: "view", id: parts[1] };
  return { name: "home" };
}

export function navigate(path) {
  window.location.hash = path;
}
