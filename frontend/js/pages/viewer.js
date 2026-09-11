import { fileUrl, getJob } from "../api.js";
import { mountViewer } from "../viewer/scene.js?v=9";

const WALK_HINT = "Click a spot to go there · drag to look · WASD to move · ↑↓ up and down";

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

async function sceneOnServer(url) {
  try {
    const res = await fetch(url, { method: "HEAD" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function renderExampleViewer(root, scene) {
  const key = String(scene || "").toLowerCase();
  const meta = EXAMPLE_META[key];
  if (!meta) {
    root.innerHTML = `
      <div class="page">
        <p class="home-label">Examples</p>
        <h1>No such scene.</h1>
        <p class="lede">That example does not exist. Pick one from the list instead.</p>
        <div class="cover-acts"><a class="act fill" href="#/examples">Back to examples</a></div>
      </div>`;
    return () => {};
  }
  if (!(await sceneOnServer(`/sample/${key}.splat`))) {
    root.innerHTML = `
      <div class="page">
        <p class="home-label">Examples</p>
        <h1>${meta.name} is not on this server.</h1>
        <p class="lede">
          These scenes are only kept on the computer that builds the models, so this copy of
          the site cannot open them. Watch the sample video or upload your own orbit instead.
        </p>
        <div class="cover-acts">
          <a class="act fill" href="#/watch/orbit">Watch sample video</a>
          <a class="act line" href="#/upload">Upload a video</a>
          <a class="act text" href="#/examples">Back to examples</a>
        </div>
      </div>`;
    return () => {};
  }
  root.innerHTML = `
    <div class="viewer-layout">
      <div>
        <div class="viewport" id="viewport">
          <div class="toolbar">
            <button data-mode="splats" class="active">3D view</button>
            <button data-level="1">Level</button>
            <button data-reset="1">Reset</button>
          </div>
          <div class="measure-readout" id="measure">Phone: left stick walks · drag to look. Computer: WASD · drag to look</div>
        </div>
      </div>
      <aside class="side">
        <h1>${meta.name}</h1>
        <p class="side-sub">Ready-made example</p>
        <dl>
          <dt>Detail</dt><dd>${meta.points.toLocaleString()} points</dd>
          <dt>Sizes</dt><dd>relative, not real-world</dd>
        </dl>
        <p class="note">Drag the left stick to walk forward and back. Drag the rest of the screen to look around.</p>
        <p class="downloads-label">More examples</p>
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
    readout.textContent = "The 3D view could not open. Reload the page to try again.";
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
    root.innerHTML = `
      <div class="page">
        <p class="home-label">Job ${id}</p>
        <h1>Not ready yet.</h1>
        <p class="lede">This model is still being built. The progress page shows the time left.</p>
        <div class="cover-acts"><a class="act fill" href="#/jobs/${id}">Back to progress</a></div>
      </div>`;
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
  const realMesh = Boolean(job.result?.confidence?.mesh) && Number(job.triangle_count || metrics.meshTriangles || 0) >= 40;
  const meshPrimary = !photoreal && realMesh && (hasGlb || hasMesh);
  const initialMode = photoreal ? "splats" : meshPrimary ? "mesh" : "points";
  const showSplatUi = photoreal;
  const showMeshUi = meshPrimary;
  const textured = Boolean(job.result?.confidence?.textured || metrics.textured);
  const kind = photoreal
    ? "Photoreal scene"
    : textured && meshPrimary
      ? "3D model with photo colours"
      : meshPrimary
        ? "3D model"
        : "Early preview";
  const triangles = Number(metrics.meshTriangles || job.triangle_count || 0);
  const densePoints = Number(metrics.densePoints || job.point_count || 0);
  const inputFrames = Number(metrics.inputFrames || job.frame_count || 0);
  root.innerHTML = `
    <div class="viewer-layout">
      <div>
        <div class="viewport" id="viewport">
          <div class="toolbar">
            ${showMeshUi ? `<button data-view="model" class="active">3D model</button>` : ""}
            ${!photoreal && (hasMesh || hasGlb) ? `<button data-view="mesh">Mesh</button>` : ""}
            ${!photoreal && job.result?.files?.pointcloud ? `<button data-view="dense">Dense</button>` : ""}
            ${showSplatUi ? `<button data-mode="splats" class="active">3D view</button>` : ""}
            ${!showSplatUi && !showMeshUi ? `<button data-mode="points" class="active">Points</button>` : ""}
            ${showSplatUi ? `<button data-level="1">Level</button>` : ""}
            <button data-reset="1">Reset</button>
          </div>
          <div class="measure-readout" id="measure">${showSplatUi ? "Phone: left stick walks · drag to look · pinch to zoom. Computer: WASD walks · drag to look" : WALK_HINT}</div>
        </div>
      </div>
      <aside class="side">
        <h1>${job.name}</h1>
        <p class="side-sub">${kind}</p>
        <dl>
          <dt>Detail</dt>
          <dd>${showMeshUi && triangles ? `${triangles.toLocaleString()} surfaces` : `${densePoints.toLocaleString()} points`}</dd>
          ${inputFrames ? `<dt>Photos used</dt><dd>${inputFrames.toLocaleString()}</dd>` : ""}
          <dt>Sizes</dt><dd>${job.has_gps ? "real-world, from the flight log" : "relative, not real-world"}</dd>
        </dl>
        <p class="downloads-label">Downloads</p>
        <div class="downloads">
          ${hasGlb ? `<a href="${fileUrl(id, "model.glb")}" download>3D model · best for sharing (.glb)</a>` : ""}
          ${hasMesh ? `<a href="${fileUrl(id, "mesh.obj")}" download>3D model for other apps (.obj)</a>` : ""}
          <a href="${fileUrl(id, "pointcloud.ply")}" download>Point cloud (.ply)</a>
          ${hasSplat && photoreal ? `<a href="${fileUrl(id, splatName)}" download>Photoreal scene (.splat)</a>` : ""}
        </div>
      </aside>
    </div>
  `;

  const viewport = root.querySelector("#viewport");
  const readout = root.querySelector("#measure");
  const glbUrl = hasGlb ? fileUrl(id, "model.glb") + `?t=${encodeURIComponent(job.updated_at)}&tex=1` : null;
  const meshUrl = hasMesh && job.result?.files?.mesh ? fileUrl(id, job.result.files.mesh) + `?t=${encodeURIComponent(job.updated_at)}` : null;
  const denseUrl = fileUrl(id, "pointcloud.ply") + `?t=${encodeURIComponent(job.updated_at)}`;
  const viewerOpts = {
    units,
    yUp: Boolean(job.result?.photoreal),
    scene: photoreal ? exampleScene : hasSplat ? "preview" : exampleScene,
    initialMode,
    preview: previewOnly,
    flyMode: !photoreal,
    onFly() {
      readout.textContent = "Moving there…";
    },
    onLook() {
      readout.textContent = "Drag to look · WASD to move · ↑↓ up and down · Reset to go back";
    },
    onReady() {
      readout.textContent = showSplatUi
        ? "Phone: left stick walks · drag to look. Computer: WASD · drag to look"
        : WALK_HINT;
    },
  };

  async function openView(kind) {
    const urlsByKind = {
      model: photoreal
        ? { splat: sampleSplat || (hasSplat ? fileUrl(id, splatName) : null) }
        : meshUrl
          ? { mesh: meshUrl }
          : { glb: glbUrl, pointcloud: denseUrl },
      mesh: { mesh: meshUrl },
      dense: { pointcloud: denseUrl },
    };
    const urls = urlsByKind[kind] || urlsByKind.model;
    const opts = { ...viewerOpts, initialMode: kind === "dense" ? "points" : kind === "mesh" ? "mesh" : initialMode };
    if (kind === "dense") {
      opts.onReady = () => {
        readout.textContent = WALK_HINT;
      };
    } else if (kind === "mesh") {
      opts.onReady = () => {
        readout.textContent = WALK_HINT;
      };
    }
    if (viewer) viewer.dispose();
    viewer = await mountViewer(viewport, urls, opts);
  }

  let viewer;
  try {
    await openView("model");
  } catch (err) {
    console.error(err);
    readout.textContent = "The 3D view could not open. Reload the page to try again.";
    return () => {};
  }

  root.querySelectorAll(".toolbar button[data-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      root.querySelectorAll(".toolbar button[data-mode]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      void viewer.setMode(btn.dataset.mode);
    });
  });
  root.querySelectorAll(".toolbar button[data-view]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      root.querySelectorAll(".toolbar button[data-view]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      try {
        await openView(btn.dataset.view);
      } catch (err) {
        console.error(err);
        readout.textContent = "That view could not open. Try 3D model.";
      }
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
  const levelBtn = root.querySelector("[data-level]");
  if (levelBtn) {
    levelBtn.addEventListener("click", () => {
      viewer.levelView?.();
      readout.textContent = "Horizon leveled";
    });
  }
  root.querySelector("[data-reset]").addEventListener("click", () => {
    viewer.resetView();
    readout.textContent = WALK_HINT;
  });

  return () => viewer.dispose();
}
