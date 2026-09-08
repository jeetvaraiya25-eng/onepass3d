import { fileUrl, getJob } from "../api.js";
import { mountViewer } from "../viewer/scene.js";

function sceneFromJob(job) {
  const fromMeta = job.result?.scene || job.result?.geo?.scene || job.demo_scene;
  if (fromMeta) return fromMeta;
  const name = (job.name || "").toLowerCase();
  if (name.includes("room")) return "room";
  if (name.includes("truck")) return "truck";
  if (name.includes("plush")) return "plush";
  if (name.includes("train")) return "train";
  return "";
}

const EXAMPLE_META = {
  train: { name: "Train station", points: 1026508 },
  truck: { name: "Truck", points: 2541226 },
  room: { name: "Room", points: 1593376 },
  plush: { name: "Plush", points: 281498 },
};

export async function renderExampleViewer(root, scene) {
  const key = String(scene || "").toLowerCase();
  const meta = EXAMPLE_META[key];
  if (!meta) {
    root.innerHTML = `<p class="lede">Unknown example.</p><a href="#/examples">Back to examples</a>`;
    return () => {};
  }
  root.innerHTML = `
    <div class="viewer-layout">
      <div>
        <div class="viewport" id="viewport">
          <div class="toolbar">
            <button data-mode="splats" class="active">Gaussians</button>
            <button data-level="1">Level</button>
            <button data-reset="1">Reset</button>
          </div>
          <div class="measure-readout" id="measure">Phone: left stick walks · drag to look. Computer: WASD · drag to look</div>
        </div>
      </div>
      <aside class="side card">
        <h2>${meta.name}</h2>
        <p class="side-sub">Trained 3DGS · example</p>
        <dl>
          <dt>Gaussians</dt><dd>${meta.points.toLocaleString()}</dd>
          <dt>Units</dt><dd>scene units</dd>
        </dl>
        <p class="note">Drag the left stick to walk forward and back. Drag the rest of the screen to look around.</p>
        <p class="downloads-label">Library</p>
        <div class="downloads">
          <a href="#/examples">All examples</a>
        </div>
      </aside>
    </div>
  `;
  const viewport = root.querySelector("#viewport");
  const readout = root.querySelector("#measure");
  let viewer;
  try {
    viewer = await mountViewer(
      viewport,
      { splat: `/sample/${key}.splat` },
      {
        units: "scene units",
        yUp: true,
        scene: key,
        initialMode: "splats",
        preview: false,
        flyMode: false,
        onReady() {
          readout.textContent = "Phone: left stick walks · drag to look. Computer: WASD · drag to look";
        },
      }
    );
  } catch (err) {
    console.error(err);
    readout.textContent = `Viewer failed: ${err.message || err}`;
    return () => {};
  }
  root.querySelector("[data-reset]").addEventListener("click", () => viewer.resetView());
  const levelBtn = root.querySelector("[data-level]");
  if (levelBtn) levelBtn.addEventListener("click", () => viewer.levelView?.());
  return () => viewer.dispose();
}

export async function renderViewer(root, id) {
  const job = await getJob(id);
  if (job.status !== "done") {
    root.innerHTML = `<p class="lede">This job is not ready yet.</p><a href="#/jobs/${id}">Back to progress</a>`;
    return () => {};
  }
  const units = job.result?.units || (job.metric ? "meters" : "relative units");
  const photoreal = Boolean(job.result?.photoreal);
  const hasSplat = Boolean(job.result?.files?.splat);
  const hasMesh = Boolean(job.result?.files?.mesh);
  const previewOnly = Boolean(job.result?.confidence?.preview) || (!photoreal && !hasSplat);
  const splatName = job.result?.files?.splat || "scene.splat";
  const exampleScene = sceneFromJob(job);
  const sampleSplat = photoreal && exampleScene ? `/sample/${exampleScene}.splat` : null;
  const gaussiansName = hasSplat ? splatName : "gaussians.ply";
  const initialMode = photoreal || hasSplat ? "splats" : hasMesh && !previewOnly ? "mesh" : "points";
  const showSplatUi = photoreal || hasSplat;
  const denseCpu = hasSplat && !photoreal;
  root.innerHTML = `
    <div class="viewer-layout">
      <div>
        <div class="viewport" id="viewport">
          <div class="toolbar">
            ${showSplatUi ? "" : `<button data-mode="points" class="${initialMode === "points" ? "active" : ""}">Points</button>`}
            ${showSplatUi ? `<button data-mode="splats" class="${initialMode === "splats" ? "active" : ""}">Gaussians</button>` : ""}
            ${hasMesh && !previewOnly ? `<button data-mode="mesh" class="${initialMode === "mesh" ? "active" : ""}">Mesh</button>` : ""}
            ${showSplatUi ? "" : `<button data-fly="1">Orbit</button>`}
            ${showSplatUi ? "" : `<button data-measure="1">Measure</button>`}
            ${showSplatUi ? `<button data-level="1">Level</button>` : ""}
            <button data-reset="1">Reset</button>
          </div>
          <div class="measure-readout" id="measure">${showSplatUi ? "Phone: left stick walks · drag to look · pinch to zoom. Computer: WASD walks · drag to look" : "Drag to orbit · scroll to zoom · this is a sparse preview"}</div>
        </div>
      </div>
      <aside class="side card">
        <h2>${job.name}</h2>
        <p class="side-sub">${photoreal ? "Trained 3DGS" : denseCpu ? "Dense CPU preview" : "CPU preview"} · ${job.id}</p>
        ${
          previewOnly
            ? `<p class="notice"><span>${denseCpu ? "This is a dense CPU reconstruction of your video — you can see the layout, but it is not a trained 3DGS kitchen like Room." : "This upload is a quick CPU preview — a cloud of points, not photoreal 3D."} For photoreal quality, open <a href="#/examples">Room, Train, Truck, or Plush</a>.</span></p>`
            : ""
        }
        <dl>
          <dt>${showSplatUi ? "Gaussians" : "Points"}</dt><dd>${job.point_count.toLocaleString()}</dd>
          ${hasMesh ? `<dt>Triangles</dt><dd>${job.triangle_count.toLocaleString()}</dd>` : ""}
          <dt>Frames</dt><dd>${job.frame_count || "sample"}</dd>
          <dt>GPS</dt><dd>${job.has_gps ? "locked" : "none"}</dd>
          <dt>Units</dt><dd>${units}</dd>
          ${photoreal ? "" : `<dt>Mean conf.</dt><dd>${(job.result?.confidence?.mean || 0).toFixed(2)}</dd>`}
        </dl>
        <p class="note">${job.result?.confidence?.note || ""}</p>
        <p class="downloads-label">Downloads</p>
        <div class="downloads">
          ${hasSplat ? `<a href="${fileUrl(id, splatName)}" download>Download Gaussians (.splat)</a>` : ""}
          <a href="${fileUrl(id, "pointcloud.ply")}" download>Download point cloud (.ply)</a>
          ${hasMesh ? `<a href="${fileUrl(id, "mesh.obj")}" download>Download mesh (.obj)</a>` : ""}
          ${hasSplat ? "" : `<a href="${fileUrl(id, gaussiansName)}" download>Download Gaussians (.ply)</a>`}
          <a href="${fileUrl(id, "report.json")}" download>Download report (.json)</a>
        </div>
      </aside>
    </div>
  `;

  const viewport = root.querySelector("#viewport");
  const readout = root.querySelector("#measure");
  let viewer;
  try {
    viewer = await mountViewer(
    viewport,
    {
      pointcloud: fileUrl(id, "pointcloud.ply") + `?t=${encodeURIComponent(job.updated_at)}`,
      splat: sampleSplat || (hasSplat ? fileUrl(id, splatName) : null),
      mesh: hasMesh ? fileUrl(id, job.result.files.mesh) + `?t=${encodeURIComponent(job.updated_at)}` : null,
    },
    {
      units,
      yUp: Boolean(job.result?.photoreal),
      scene: photoreal ? exampleScene : hasSplat ? "preview" : exampleScene,
      initialMode,
      preview: previewOnly,
      flyMode: false,
      onFly() {
        readout.textContent = "Moving to that point…";
        setTimeout(() => {
          if (readout.textContent.startsWith("Moving")) {
            readout.textContent = showSplatUi
              ? "Drag to look 360° · scroll to zoom · Shift+scroll for height"
              : "Drag to orbit · scroll to zoom";
          }
        }, 1100);
      },
      onMeasure(distance) {
        readout.textContent = distance == null ? "Click two points to measure" : `${distance.toFixed(2)} ${units}`;
      },
      onReady() {
        readout.textContent = showSplatUi
          ? "Phone: left stick walks · drag to look. Computer: WASD · drag to look"
          : "Drag to orbit · scroll to zoom · this is a sparse preview";
      },
    }
  );
  } catch (err) {
    console.error(err);
    readout.textContent = `Viewer failed: ${err.message || err}`;
    return () => {};
  }

  root.querySelectorAll(".toolbar button[data-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      root.querySelectorAll(".toolbar button[data-mode]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      void viewer.setMode(btn.dataset.mode);
    });
  });
  const confBtn = root.querySelector("[data-conf]");
  if (confBtn) {
    let confOn = false;
    confBtn.addEventListener("click", () => {
      confOn = !confOn;
      confBtn.classList.toggle("active", confOn);
      viewer.setConfidence(confOn);
    });
  }
  const flyBtn = root.querySelector("[data-fly]");
  const measureBtn = root.querySelector("[data-measure]");
  if (flyBtn && measureBtn) {
    let measureOn = false;
    flyBtn.addEventListener("click", () => {
      measureOn = false;
      measureBtn.classList.remove("active");
      flyBtn.classList.add("active");
      viewer.setFlyMode(true);
      viewer.setMeasure(false);
      readout.textContent = "Click a rooftop or the ground to fly there";
    });
    measureBtn.addEventListener("click", () => {
      measureOn = !measureOn;
      measureBtn.classList.toggle("active", measureOn);
      flyBtn.classList.toggle("active", !measureOn);
      viewer.setMeasure(measureOn);
      viewer.setFlyMode(!measureOn);
      readout.textContent = measureOn ? "Click two points to measure" : "Click a rooftop or the ground to fly there";
    });
  }
  const levelBtn = root.querySelector("[data-level]");
  if (levelBtn) {
    levelBtn.addEventListener("click", () => {
      viewer.levelView?.();
      readout.textContent = "Horizon leveled";
    });
  }
  root.querySelector("[data-reset]").addEventListener("click", () => viewer.resetView());

  return () => viewer.dispose();
}
