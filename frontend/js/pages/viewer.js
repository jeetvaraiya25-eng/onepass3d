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
  const metrics = job.result?.metrics || {};
  const hasGlb = Boolean(job.result?.files?.glb);
  const hasSplat = Boolean(job.result?.files?.splat);
  const hasMesh = Boolean(job.result?.files?.mesh || hasGlb);
  const previewOnly = Boolean(job.result?.confidence?.preview) && !hasGlb && !hasMesh;
  const splatName = job.result?.files?.splat || "scene.splat";
  const exampleScene = sceneFromJob(job);
  const sampleSplat = photoreal && exampleScene ? `/sample/${exampleScene}.splat` : null;
  const gaussiansName = hasSplat ? splatName : "gaussians.ply";
  const realMesh = Boolean(job.result?.confidence?.mesh) && Number(job.triangle_count || metrics.meshTriangles || 0) >= 40;
  const meshPrimary = !photoreal && realMesh && (hasGlb || hasMesh);
  const initialMode = photoreal ? "splats" : meshPrimary ? "mesh" : "points";
  const showSplatUi = photoreal;
  const showMeshUi = meshPrimary;
  const textured = Boolean(job.result?.confidence?.textured || metrics.textured);
  const artifact = job.result?.artifact || (photoreal ? "Trained 3DGS" : textured ? "TEXTURED 3D MESH" : meshPrimary ? "VERTEX-COLORED 3D MESH" : "CPU preview");
  const triangles = Number(metrics.meshTriangles || job.triangle_count || 0);
  const densePoints = Number(metrics.densePoints || job.point_count || 0);
  const inputFrames = Number(metrics.inputFrames || job.frame_count || 0);
  const registered = Number(metrics.registeredFrames || 0);
  const registration = metrics.registrationRatio;
  const reproj = metrics.reprojectionError;
  const components = metrics.components;
  const sparsePoints = Number(metrics.sparsePoints || 0);
  const pipeline = metrics.pipeline || job.result?.pipeline || "";
  root.innerHTML = `
    <div class="viewer-layout">
      <div>
        <div class="viewport" id="viewport">
          <div class="toolbar">
            ${showSplatUi ? `<button data-mode="splats" class="active">Gaussians</button>` : ""}
            ${showMeshUi ? `<button data-mode="mesh" class="active">FINAL</button>` : ""}
            ${!photoreal && job.result?.files?.sparse ? `<button data-diag="sparse">SPARSE</button>` : ""}
            ${!photoreal && job.result?.files?.pointcloud ? `<button data-diag="dense">DENSE</button>` : ""}
            ${!photoreal && (hasMesh || hasGlb) ? `<button data-diag="mesh">MESH</button>` : ""}
            ${!showSplatUi && !showMeshUi ? `<button data-mode="points" class="active">Points</button>` : ""}
            ${showMeshUi ? `<button data-fly="1">Orbit</button>` : ""}
            ${showSplatUi ? `<button data-level="1">Level</button>` : ""}
            <button data-reset="1">Reset</button>
          </div>
          <div class="measure-readout" id="measure">${showSplatUi ? "Phone: left stick walks · drag to look · pinch to zoom. Computer: WASD walks · drag to look" : "Drag to orbit · scroll to zoom the 3D model"}</div>
        </div>
      </div>
      <aside class="side card">
        <h2>${job.name}</h2>
        <p class="side-sub">${artifact} · ${job.id}</p>
        <dl>
          <dt>${showSplatUi ? "Gaussians" : showMeshUi ? "Mesh triangles" : "Points"}</dt>
          <dd>${(showMeshUi ? triangles : densePoints).toLocaleString()}</dd>
          ${showMeshUi && densePoints ? `<dt>Dense points</dt><dd>${densePoints.toLocaleString()}</dd>` : ""}
          ${showMeshUi && sparsePoints ? `<dt>Sparse points</dt><dd>${sparsePoints.toLocaleString()}</dd>` : ""}
          <dt>Input frames</dt><dd>${inputFrames || (photoreal ? "sample" : "—")}</dd>
          ${registered ? `<dt>Registered cameras</dt><dd>${registered.toLocaleString()}</dd>` : ""}
          ${registration != null && !photoreal ? `<dt>Registration</dt><dd>${Math.round(Number(registration) * 100)}%</dd>` : ""}
          ${reproj != null && !photoreal ? `<dt>Reprojection error</dt><dd>${Number(reproj).toFixed(2)} px</dd>` : ""}
          ${components != null && !photoreal ? `<dt>Components</dt><dd>${components}</dd>` : ""}
          <dt>GPS</dt><dd>${job.has_gps ? "locked" : "none"}</dd>
          <dt>Scale</dt><dd>${units}</dd>
          ${pipeline && !photoreal ? `<dt>Pipeline</dt><dd>${pipeline}</dd>` : ""}
          ${metrics.qualityScore != null ? `<dt>Quality</dt><dd>${metrics.qualityScore}/100 · ${metrics.qualityStatus || ""}</dd>` : ""}
        </dl>
        <p class="note">${job.result?.confidence?.note || ""}</p>
        <p class="downloads-label">Downloads</p>
        <div class="downloads">
          ${hasGlb ? `<a href="${fileUrl(id, "model.glb")}" download>Download 3D model (.glb)</a>` : ""}
          ${hasMesh ? `<a href="${fileUrl(id, "mesh.obj")}" download>Download mesh (.obj)</a>` : ""}
          <a href="${fileUrl(id, "pointcloud.ply")}" download>Download point cloud (.ply)</a>
          ${hasSplat && photoreal ? `<a href="${fileUrl(id, splatName)}" download>Download Gaussians (.splat)</a>` : ""}
          ${hasSplat && !photoreal ? "" : hasSplat ? "" : `<a href="${fileUrl(id, gaussiansName)}" download>Download Gaussians (.ply)</a>`}
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
      splat: sampleSplat || (photoreal && hasSplat ? fileUrl(id, splatName) : null),
      mesh: hasMesh && job.result?.files?.mesh ? fileUrl(id, job.result.files.mesh) + `?t=${encodeURIComponent(job.updated_at)}` : null,
      glb: hasGlb ? fileUrl(id, "model.glb") + `?t=${encodeURIComponent(job.updated_at)}&tex=1` : null,
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
          : "Drag to orbit · scroll to zoom the 3D model";
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

  root.querySelectorAll("[data-diag]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const kind = btn.dataset.diag;
      root.querySelectorAll(".toolbar button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const urls = {
        sparse: { pointcloud: fileUrl(id, "sparse.ply") + `?t=${encodeURIComponent(job.updated_at)}` },
        dense: { pointcloud: fileUrl(id, "pointcloud.ply") + `?t=${encodeURIComponent(job.updated_at)}` },
        mesh: {
          mesh: job.result?.files?.mesh ? fileUrl(id, job.result.files.mesh) + `?t=${encodeURIComponent(job.updated_at)}` : null,
        },
      }[kind];
      readout.textContent = kind === "sparse" ? "Sparse COLMAP points" : kind === "dense" ? "Dense point cloud" : "Raw mesh";
      try {
        viewer.dispose();
        viewer = await mountViewer(viewport, urls, { units, yUp: false, initialMode: kind === "mesh" ? "mesh" : "points", preview: false });
      } catch (err) {
        readout.textContent = `Diagnostic view failed: ${err.message || err}`;
      }
    });
  });
  const finalBtn = root.querySelector('[data-mode="mesh"]');
  if (finalBtn && !photoreal) {
    finalBtn.addEventListener("click", async () => {
      root.querySelectorAll("[data-diag]").forEach((b) => b.classList.remove("active"));
      try {
        viewer.dispose();
        viewer = await mountViewer(
          viewport,
          { glb: hasGlb ? fileUrl(id, "model.glb") + `?t=${encodeURIComponent(job.updated_at)}` : null },
          { units, yUp: false, initialMode: "mesh", preview: false }
        );
        readout.textContent = "Drag to orbit · scroll to zoom the 3D model";
      } catch (err) {
        readout.textContent = `Viewer failed: ${err.message || err}`;
      }
    });
  }

  return () => viewer.dispose();
}
