import { route } from "./router.js";
import { renderHome } from "./pages/home.js?v=29";
import { renderUpload } from "./pages/upload.js?v=8";
import { renderJobs, renderJob } from "./pages/job.js?v=9";
import { renderExampleViewer, renderViewer } from "./pages/viewer.js?v=10";
import { renderExamples } from "./pages/examples.js?v=6";
import { renderWatch } from "./pages/watch.js?v=6";
import { setupReveals, teardownReveals } from "./reveal.js";

const REVEAL_PAGES = new Set(["home", "examples", "watch", "upload", "jobs"]);

const app = document.getElementById("app");
let teardown = null;

function setActive() {
  const current = route();
  const viewing = current.name === "view" || current.name === "example-view";
  document.querySelectorAll(".site-nav nav a").forEach((link) => {
    const key = link.dataset.nav;
    const on =
      (key === "home" && current.name === "home") ||
      (key === "examples" && (current.name === "examples" || current.name === "watch" || current.name === "example-view")) ||
      (key === "upload" && current.name === "upload") ||
      (key === "jobs" && (current.name === "jobs" || current.name === "job" || current.name === "view"));
    link.classList.toggle("is-on", on);
  });
  document.querySelector(".shell")?.classList.toggle("is-home", current.name === "home");
  document.querySelector(".shell")?.classList.toggle("is-view", viewing);
  app.classList.toggle("full", viewing);
  app.classList.toggle("home", current.name === "home");
}

async function render() {
  if (typeof teardown === "function") {
    teardown();
    teardown = null;
  }
  const current = route();
  setActive();
  try {
    if (current.name === "home") teardown = renderHome(app);
    if (current.name === "examples") await renderExamples(app);
    if (current.name === "watch") renderWatch(app);
    if (current.name === "upload") renderUpload(app);
    if (current.name === "jobs") await renderJobs(app);
    if (current.name === "job") teardown = await renderJob(app, current.id);
    if (current.name === "view") teardown = await renderViewer(app, current.id);
    if (current.name === "example-view") teardown = await renderExampleViewer(app, current.scene);
  } catch (err) {
    console.error(err);
    const detail = String(err?.message || err || "").slice(0, 160);
    app.innerHTML = `
      <div class="page">
        <p class="home-label">Problem</p>
        <h1>This page could not open.</h1>
        <p class="lede">${detail || "Something went wrong."} Check that OnePass3D is running, then try again.</p>
        <div class="cover-acts">
          <a class="act fill" href="#/">Go home</a>
          <a class="act line" href="#/jobs">All jobs</a>
        </div>
      </div>`;
  }

  if (REVEAL_PAGES.has(current.name)) setupReveals(app);
  else teardownReveals();
}

window.addEventListener("hashchange", render);
render();
