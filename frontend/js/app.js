import { route } from "./router.js";
import { renderHome } from "./pages/home.js";
import { renderUpload } from "./pages/upload.js";
import { renderJobs, renderJob } from "./pages/job.js";
import { renderExampleViewer, renderViewer } from "./pages/viewer.js";
import { renderExamples } from "./pages/examples.js";
import { renderWatch } from "./pages/watch.js";
import { setupReveals, teardownReveals } from "./reveal.js";

const REVEAL_PAGES = new Set(["home", "examples", "watch", "upload", "jobs"]);

const app = document.getElementById("app");
let teardown = null;

function closeMenu() {
  const menu = document.getElementById("workspace-menu");
  const toggle = menu?.querySelector(".menu-toggle");
  if (!menu || !toggle) return;
  menu.classList.remove("open");
  toggle.setAttribute("aria-expanded", "false");
}

function setupMenu() {
  const menu = document.getElementById("workspace-menu");
  const toggle = menu?.querySelector(".menu-toggle");
  if (!menu || !toggle || toggle.dataset.bound) return;
  toggle.dataset.bound = "1";
  toggle.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = menu.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) closeMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu();
  });
  menu.querySelectorAll("nav a").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });
}

function setActive() {
  const current = route();
  document.querySelectorAll(".menu-panel nav a").forEach((link) => {
    const href = link.getAttribute("href");
    const on =
      (current.name === "home" && href === "#/") ||
      ((current.name === "examples" || current.name === "watch") && href === "#/examples") ||
      (current.name === "upload" && href === "#/upload") ||
      ((current.name === "jobs" || current.name === "job" || current.name === "view" || current.name === "example-view") && href === "#/jobs");
    link.classList.toggle("active", on);
  });
  closeMenu();
}

async function render() {
  if (typeof teardown === "function") {
    teardown();
    teardown = null;
  }
  const current = route();
  setActive();
  app.classList.toggle("full", current.name === "view" || current.name === "example-view");
  if (current.name === "home") renderHome(app);
  if (current.name === "examples") await renderExamples(app);
  if (current.name === "watch") renderWatch(app);
  if (current.name === "upload") renderUpload(app);
  if (current.name === "jobs") await renderJobs(app);
  if (current.name === "job") teardown = await renderJob(app, current.id);
  if (current.name === "view") teardown = await renderViewer(app, current.id);
  if (current.name === "example-view") teardown = await renderExampleViewer(app, current.scene);

  if (REVEAL_PAGES.has(current.name)) setupReveals(app);
  else teardownReveals();
}

setupMenu();
window.addEventListener("hashchange", render);
render();
