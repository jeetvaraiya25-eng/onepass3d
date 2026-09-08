import { listExamples } from "../api.js";
import { navigate } from "../router.js";
import { scanReveals } from "../reveal.js";

const FALLBACK_SCENES = [
  { id: "train", name: "Train station", gaussians: 1026508, blurb: "Photographs of a locomotive in a shed. The original 3DGS paper scene." },
  { id: "truck", name: "Truck", gaussians: 2541226, blurb: "Outdoor truck and foliage. Same photoreal quality as the train scene." },
  { id: "room", name: "Room", gaussians: 1593376, blurb: "Indoor 360 capture of a furnished room." },
  { id: "plush", name: "Plush", gaussians: 281498, blurb: "Object-scale scan. Smaller file, loads fast." },
];

export function exampleCard(scene) {
  const count = scene.gaussians ? `${scene.gaussians.toLocaleString()} Gaussians` : "Photoreal";
  return `
    <article class="card example-card">
      <p class="example-meta">${count} · real 3DGS</p>
      <h3>${scene.name}</h3>
      <p>${scene.blurb}</p>
      <div class="actions">
        <button class="btn primary" type="button" data-scene="${scene.id}">Open in 3D</button>
      </div>
    </article>
  `;
}

export function bindExampleButtons(root) {
  root.querySelectorAll("[data-scene]").forEach((button) => {
    button.addEventListener("click", () => {
      navigate(`/view/example/${button.dataset.scene}`);
    });
  });
}

export async function loadScenes() {
  try {
    const data = await listExamples();
    if (data.scenes?.length) return data.scenes;
  } catch {
    /* server may still be on an older build */
  }
  return FALLBACK_SCENES;
}

export async function renderExamples(root) {
  root.innerHTML = `
    <p class="chip">Photoreal library</p>
    <h1>Real Gaussian splats</h1>
    <p class="lede">
      Trained 3D Gaussian Splatting scenes reconstructed from photographs. Open one to
      fly through it. These are not produced by uploading the sample drone video on this
      machine — that path runs a CPU preview.
    </p>
    <div class="grid-2" id="example-grid" style="margin-top:34px">
      <article class="card"><p>Loading scenes…</p></article>
    </div>

    <section class="section">
      <div class="section-head">
        <div>
          <h2>Sample flight video</h2>
          <p>Watch the orbit clip first so you know exactly what you have, then download it.</p>
        </div>
      </div>
      <div class="actions" style="margin-top:0">
        <a class="btn primary" href="#/watch/orbit">Watch sample orbit</a>
        <a class="btn ghost" href="#/upload">Process your own flight</a>
      </div>
    </section>
  `;
  const scenes = await loadScenes();
  root.querySelector("#example-grid").innerHTML = scenes.map(exampleCard).join("");
  bindExampleButtons(root);
  scanReveals();
}
