import { exampleCard, bindExampleButtons, loadScenes } from "./examples.js";
import { scanReveals } from "../reveal.js";

export function renderHome(root) {
  root.innerHTML = `
    <h1>One orbit in. Metric 3D out.</h1>
    <p class="lede">
      OnePass3D turns a single drone orbit — or a photo set from that pass — into a
      georeferenced 3D model: textured mesh, Gaussian splat file, and measurements,
      without a mapping grid or ground control points.
    </p>
    <div class="actions">
      <a class="btn primary" href="#/examples">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.8 21 7.4v9.2L12 21.2 3 16.6V7.4z"/><path d="M3 7.4l9 4.6 9-4.6M12 12v9.2"/></svg>
        Open photoreal examples
      </a>
      <a class="btn ghost" href="#/watch/orbit">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 8.5l6 3.5-6 3.5z"/><circle cx="12" cy="12" r="9"/></svg>
        Watch sample orbit
      </a>
      <a class="btn ghost" href="#/upload">Process a flight</a>
    </div>

    <dl class="stats">
      <div><dt>Input</dt><dd>1080p / 4K<small>single-pass video or stills</small></dd></div>
      <div><dt>Geo lock</dt><dd>GPS · SRT / CSV / GPX<small>metric scale without GCPs</small></dd></div>
      <div><dt>Outputs</dt><dd>Mesh · Cloud · Splat<small>plus a JSON report</small></dd></div>
      <div><dt>Photoreal library</dt><dd>4 scenes<small>real trained 3DGS</small></dd></div>
    </dl>

    <section class="section">
      <div class="section-head">
        <div>
          <h2>Photoreal Gaussian examples</h2>
          <p>
            Real 3D Gaussian Splatting trained on photographs — the quality you saw in
            the train scene. Click one to open it in the viewer.
          </p>
        </div>
        <a class="link" href="#/examples">All examples →</a>
      </div>
      <div class="grid-2" id="example-grid">
        <article class="card"><p>Loading scenes…</p></article>
      </div>
    </section>

    <section class="capture">
      <div class="section-head">
        <div>
          <h2>Fly like this</h2>
          <p>
            A <strong>Point of Interest orbit</strong>: the aircraft circles the subject
            while the camera yaws to keep it centred. That overlap is what
            reconstruction needs — not a one-way cinematic pass.
          </p>
        </div>
      </div>
      <div class="capture-grid">
        <article class="card capture-card">
          <h3>DJI Mini 4 Pro orbit</h3>
          <div class="capture-frame portrait">
            <iframe
              src="https://www.youtube.com/embed/ZV2BgGGax1s"
              title="How to do a drone orbit transition — DJI Mini 4 Pro"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              referrerpolicy="strict-origin-when-cross-origin"
              allowfullscreen
            ></iframe>
          </div>
          <p>
            Slow circle, subject locked in frame.
            <a href="https://www.youtube.com/shorts/ZV2BgGGax1s" target="_blank" rel="noreferrer">Watch on YouTube</a>.
          </p>
        </article>
        <article class="card capture-card">
          <h3>Sample orbit you can upload</h3>
          <p>
            A licensed drone orbit around a chimney. Watch it full-size first, then
            download the file if you want it on disk.
          </p>
          <div class="meta-row">
            <span class="tag">1080p</span>
            <span class="tag">60 fps</span>
            <span class="tag">Pexels licence</span>
          </div>
          <div class="actions" style="margin-top:20px">
            <a class="btn primary" href="#/watch/orbit">Watch sample orbit</a>
          </div>
        </article>
      </div>
    </section>
  `;
  void loadScenes().then((scenes) => {
    const grid = root.querySelector("#example-grid");
    if (!grid) return;
    grid.innerHTML = scenes.map(exampleCard).join("");
    bindExampleButtons(root);
    scanReveals();
  });
}
