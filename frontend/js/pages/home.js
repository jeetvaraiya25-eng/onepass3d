import { exampleIndex as sceneRow, loadScenes } from "./examples.js?v=6";
import { scanReveals } from "../reveal.js";
import { mountCover } from "../cover/mission.js?v=21";

const NOTES = {
  orbit: {
    label: "Upload",
    title: "Upload your orbit.",
    body: "Fly a slow circle. Keep the subject in the middle of the frame the whole way.",
    href: "#/upload",
    link: "Upload a video",
  },
  mesh: {
    label: "Jobs",
    title: "Watch it being built.",
    body: "It works out the camera path first, then fills in the surface. Open Jobs to see the time left.",
    href: "#/jobs",
    link: "Open jobs",
  },
  scene: {
    label: "Examples",
    title: "Open a 3D scene.",
    body: "Ready-made scenes you can fly through in the viewer.",
    href: "#/examples",
    link: "Open examples",
  },
};

export function renderHome(root) {
  root.innerHTML = `
    <section class="cover" aria-label="OnePass3D">
      <div class="cover-stage" id="cover-stage"></div>
      <div class="cover-hud" id="cover-hud">
        <div class="cover-left">
          <p class="cover-meta">OnePass3D / One orbit into a 3D model</p>
          <h1>One orbit.<br />The complete scene.</h1>
          <p class="cover-lede">Fly a slow circle. Keep the subject in frame. OnePass3D builds the 3D model from that orbit.</p>
          <div class="cover-acts">
            <a class="act fill" href="#/upload">Upload a video</a>
            <a class="act line" href="#/examples">Open examples</a>
            <a class="act text" href="#/watch/orbit">Watch sample video</a>
          </div>
        </div>
        <aside class="cover-right">
          <p class="cover-aside-kicker">One orbit. Every surface.</p>
          <div class="exhibit">
            <i class="exhibit-back"></i>
            <i class="exhibit-mid"></i>
            <div class="exhibit-card">
              <p>onepass3d</p>
              <strong>One orbit. The complete scene.</strong>
              <div class="exhibit-stage">
                <video
                  class="exhibit-film"
                  src="/media/orbit-loop.mp4"
                  muted
                  loop
                  playsinline
                  preload="auto"
                  disablepictureinpicture
                ></video>
              </div>
              <em>Orbit</em>
            </div>
          </div>
          <div class="cover-tabs" role="tablist">
            <button type="button" class="is-on" data-note="orbit">Upload</button>
            <button type="button" data-note="mesh">Jobs</button>
            <button type="button" data-note="scene">Examples</button>
          </div>
          <p class="cover-note-label" data-note-label>Upload</p>
          <h2 data-note-title>Upload your orbit.</h2>
          <p class="cover-note-body" data-note-body>Fly a slow circle. Keep the subject in the middle of the frame the whole way.</p>
          <a class="cover-note-link" data-note-link href="#/upload">Upload a video <span>↗</span></a>
        </aside>
      </div>
      <p class="cover-foot">
        <span>Upload</span>
        <span>Rebuild</span>
        <span>View</span>
        <span>Measure</span>
      </p>
    </section>

    <div class="home-body">
      <p class="home-label">Start here</p>
      <section class="doors">
        <a class="door" href="#/upload">
          <b class="door-sweep" aria-hidden="true"></b>
          <header><span>01</span><i aria-hidden="true">→</i></header>
          <h2>Upload a video</h2>
          <p>Fly a slow circle around the subject and keep it in the middle of the frame.</p>
          <em>upload</em>
        </a>
        <a class="door" href="#/examples">
          <b class="door-sweep" aria-hidden="true"></b>
          <header><span>02</span><i aria-hidden="true">→</i></header>
          <h2>Open examples</h2>
          <p>Ready-made 3D scenes you can fly through in the viewer.</p>
          <em>examples</em>
        </a>
        <a class="door" href="#/watch/orbit">
          <b class="door-sweep" aria-hidden="true"></b>
          <header><span>03</span><i aria-hidden="true">→</i></header>
          <h2>Sample video</h2>
          <p>Watch the Ignatius orbit first, then fly the same way.</p>
          <em>watch</em>
        </a>
      </section>

      <p class="home-label">Examples</p>
      <section class="index" id="example-grid">
        <a class="index-row"><span>00</span><div><h3>Loading scenes…</h3></div></a>
      </section>
    </div>
  `;

  const stage = root.querySelector("#cover-stage");
  const hud = root.querySelector("#cover-hud");
  const film = root.querySelector(".exhibit-film");
  const stopCover = stage ? mountCover(stage, hud) : () => {};
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const onFilmVis = () => {
    if (!film) return;
    if (document.hidden || still) film.pause();
    else void film.play().catch(() => {});
  };
  if (film) {
    film.muted = true;
    if (!still) void film.play().catch(() => {});
    document.addEventListener("visibilitychange", onFilmVis);
  }

  root.querySelectorAll("[data-note]").forEach((button) => {
    button.addEventListener("click", () => {
      const note = NOTES[button.dataset.note];
      if (!note) return;
      root.querySelectorAll(".cover-tabs button").forEach((el) => el.classList.toggle("is-on", el === button));
      const label = root.querySelector("[data-note-label]");
      const title = root.querySelector("[data-note-title]");
      const body = root.querySelector("[data-note-body]");
      const link = root.querySelector("[data-note-link]");
      if (label) label.textContent = note.label;
      if (title) title.textContent = note.title;
      if (body) body.textContent = note.body;
      if (link) {
        link.href = note.href;
        link.innerHTML = `${note.link} <span>↗</span>`;
      }
    });
  });

  void loadScenes().then((scenes) => {
    const grid = root.querySelector("#example-grid");
    if (!grid) return;
    grid.innerHTML = scenes.map((scene, index) => sceneRow(scene, index)).join("");
    scanReveals();
  });

  return () => {
    document.removeEventListener("visibilitychange", onFilmVis);
    film?.pause();
    stopCover();
  };
}
