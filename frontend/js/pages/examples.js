import { listExamples } from "../api.js";
import { scanReveals } from "../reveal.js";

const FALLBACK_SCENES = [
  { id: "train", name: "Train station", gaussians: 1026508, blurb: "Photographs of a train engine parked inside a shed." },
  { id: "truck", name: "Truck", gaussians: 2541226, blurb: "A truck outdoors with trees behind it." },
  { id: "room", name: "Room", gaussians: 1593376, blurb: "A furnished room, filmed all the way around." },
  { id: "plush", name: "Plush", gaussians: 281498, blurb: "A small soft toy. This one opens the fastest." },
];

export function exampleIndex(scene, index) {
  const n = String(index + 1).padStart(2, "0");
  const ready = scene.ready !== false;
  if (!ready) {
    return `
      <div class="index-row is-off">
        <span>${n}</span>
        <div>
          <h3>${scene.name}</h3>
          <p>Not on this server. These scenes are only kept on the computer that builds the models.</p>
        </div>
        <em>unavailable</em>
      </div>
    `;
  }
  return `
    <a class="index-row" href="#/view/example/${scene.id}">
      <span>${n}</span>
      <div>
        <h3>${scene.name}</h3>
        <p>${scene.blurb}</p>
      </div>
      <i aria-hidden="true">→</i>
    </a>
  `;
}

export async function loadScenes() {
  try {
    const data = await listExamples();
    // the server only decides which scenes exist; the words shown come from here
    if (data.scenes?.length) {
      return data.scenes.map((scene) => {
        const local = FALLBACK_SCENES.find((item) => item.id === scene.id);
        return local ? { ...scene, name: local.name, blurb: local.blurb } : scene;
      });
    }
  } catch {
    /* server may still be on an older build */
  }
  return FALLBACK_SCENES;
}

export async function renderExamples(root) {
  root.innerHTML = `
    <div class="page">
      <p class="home-label">Examples</p>
      <h1>Open a 3D scene.</h1>
      <p class="lede">Ready-made scenes you can fly through in the viewer.</p>
      <section class="index" id="example-grid">
        <a class="index-row"><span>00</span><div><h3>Loading scenes…</h3></div></a>
      </section>
      <p class="lede" id="example-note" hidden></p>
      <div class="cover-acts">
        <a class="act fill" href="#/watch/orbit">Watch sample video</a>
        <a class="act line" href="#/upload">Upload a video</a>
      </div>
    </div>
  `;
  const scenes = await loadScenes();
  const grid = root.querySelector("#example-grid");
  if (grid) grid.innerHTML = scenes.map((scene, index) => exampleIndex(scene, index)).join("");
  const missing = scenes.filter((scene) => scene.ready === false).length;
  const note = root.querySelector("#example-note");
  if (note && missing) {
    note.hidden = false;
    note.textContent =
      missing === scenes.length
        ? "None of the example scenes are on this server yet. Watch the sample video or upload your own orbit instead."
        : missing === 1
          ? "One of these scenes is not on this server. The rest open normally."
          : `${missing} of these scenes are not on this server. The rest open normally.`;
  }
  scanReveals();
}
