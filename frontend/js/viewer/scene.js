import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";

export async function mountViewer(container, urls, options) {
  if (urls.splat) return mountSplatViewer(container, urls, options);
  return mountMeshViewer(container, urls, options);
}

function createStage(container, { yUp, antialias }) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x07080b);
  const camera = new THREE.PerspectiveCamera(55, 1, 0.05, 8000);
  camera.up.set(0, yUp ? 1 : 0, yUp ? 0 : 1);

  const renderer = new THREE.WebGLRenderer({
    antialias,
    alpha: false,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, antialias ? 2 : 1.25));
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;

  const status = document.createElement("div");
  status.className = "load-status";
  container.appendChild(status);

  function resize() {
    const w = container.clientWidth;
    const h = container.clientHeight;
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  }
  resize();
  const ro = new ResizeObserver(resize);
  ro.observe(container);

  return { scene, camera, renderer, controls, status, resize, ro };
}

function setStatus(el, text, isError) {
  if (!el) return;
  el.textContent = text || "";
  el.classList.toggle("error", Boolean(isError));
  el.style.display = text ? "block" : "none";
}

function bindFlyAndMeasure({ renderer, camera, controls, scene, options, yUp, getPickTargets, getRadius, status }) {
  const measure = {
    active: false,
    picks: [],
    markers: new THREE.Group(),
    line: null,
    distance: null,
  };
  scene.add(measure.markers);
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let flyMode = options.flyMode !== false;
  let pointerDown = null;
  let flying = false;

  function flyTo(point) {
    const radius = getRadius();
    const startPos = camera.position.clone();
    const startTarget = controls.target.clone();
    const dist = Math.max(radius * 0.18, 4);
    const offset = yUp
      ? new THREE.Vector3(dist * 0.22, dist * 0.42, dist * 0.72)
      : new THREE.Vector3(dist * 0.15, -dist * 0.85, dist * 0.55);
    const endPos = point.clone().add(offset);
    flying = true;
    controls.enabled = false;
    const t0 = performance.now();
    function tick(now) {
      const u = Math.min(1, (now - t0) / 900);
      const e = 1 - Math.pow(1 - u, 3);
      camera.position.lerpVectors(startPos, endPos, e);
      controls.target.lerpVectors(startTarget, point, e);
      if (u < 1) requestAnimationFrame(tick);
      else {
        flying = false;
        controls.enabled = true;
      }
    }
    requestAnimationFrame(tick);
    if (options.onFly) options.onFly(point);
  }

  function pick(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    raycaster.params.Points.threshold = Math.max(getRadius() * 0.012, 0.25);
    const hits = raycaster.intersectObjects(getPickTargets(), true);
    return hits.length ? hits[0].point.clone() : null;
  }

  function resetMeasure() {
    measure.picks = [];
    measure.distance = null;
    measure.markers.clear();
    measure.line = null;
    if (options.onMeasure) options.onMeasure(null);
  }

  function onPointerDown(event) {
    pointerDown = { x: event.clientX, y: event.clientY };
  }

  function onPointerUp(event) {
    if (!pointerDown || flying) return;
    const dx = event.clientX - pointerDown.x;
    const dy = event.clientY - pointerDown.y;
    pointerDown = null;
    if (dx * dx + dy * dy > 25) return;
    const point = pick(event);
    if (!point) return;
    if (measure.active) {
      if (measure.picks.length >= 2) resetMeasure();
      measure.picks.push(point);
      const radius = getRadius();
      const dot = new THREE.Mesh(
        new THREE.SphereGeometry(Math.max(radius * 0.008, 0.08)),
        new THREE.MeshBasicMaterial({ color: 0xc4f542 })
      );
      dot.position.copy(point);
      measure.markers.add(dot);
      if (measure.picks.length === 2) {
        const geom = new THREE.BufferGeometry().setFromPoints(measure.picks);
        measure.line = new THREE.Line(geom, new THREE.LineBasicMaterial({ color: 0xc4f542 }));
        measure.markers.add(measure.line);
        measure.distance = measure.picks[0].distanceTo(measure.picks[1]);
        if (options.onMeasure) options.onMeasure(measure.distance);
      }
      return;
    }
    if (flyMode) flyTo(point);
  }

  renderer.domElement.addEventListener("pointerdown", onPointerDown);
  renderer.domElement.addEventListener("pointerup", onPointerUp);
  renderer.domElement.style.cursor = "pointer";

  return {
    measure,
    resetMeasure,
    setFlyMode(on) {
      flyMode = on;
      if (on) {
        measure.active = false;
        resetMeasure();
        renderer.domElement.style.cursor = "pointer";
      }
    },
    setMeasure(on) {
      measure.active = on;
      if (on) flyMode = false;
      if (!on) resetMeasure();
      renderer.domElement.style.cursor = on ? "crosshair" : "pointer";
    },
    dispose() {
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
    },
    status,
  };
}

function robustPointBounds(pos) {
  const n = pos?.count || 0;
  const xs = [];
  const ys = [];
  const zs = [];
  const step = Math.max(1, Math.floor(n / 25000));
  for (let i = 0; i < n; i += step) {
    xs.push(pos.getX(i));
    ys.push(pos.getY(i));
    zs.push(pos.getZ(i));
  }
  const pct = (arr, p) => {
    arr.sort((a, b) => a - b);
    return arr[Math.max(0, Math.min(arr.length - 1, Math.floor((arr.length - 1) * p)))];
  };
  if (xs.length < 8) {
    return { center: new THREE.Vector3(), radius: 8 };
  }
  const min = new THREE.Vector3(pct(xs, 0.06), pct(ys, 0.06), pct(zs, 0.06));
  const max = new THREE.Vector3(pct(xs, 0.94), pct(ys, 0.94), pct(zs, 0.94));
  return {
    center: min.clone().add(max).multiplyScalar(0.5),
    radius: Math.max(max.distanceTo(min) * 0.55, 1.6),
  };
}

function robustLocalBounds(mesh) {
  const xs = [];
  const ys = [];
  const zs = [];
  if (typeof mesh.forEachSplat === "function") {
    mesh.forEachSplat((index, center) => {
      if (index & 31) return;
      xs.push(center.x);
      ys.push(center.y);
      zs.push(center.z);
    });
  }
  const pct = (arr, p) => {
    arr.sort((a, b) => a - b);
    return arr[Math.max(0, Math.min(arr.length - 1, Math.floor((arr.length - 1) * p)))];
  };
  if (xs.length > 32) {
    const min = new THREE.Vector3(pct(xs, 0.05), pct(ys, 0.05), pct(zs, 0.05));
    const max = new THREE.Vector3(pct(xs, 0.95), pct(ys, 0.95), pct(zs, 0.95));
    return {
      center: min.clone().add(max).multiplyScalar(0.5),
      radius: Math.max(max.distanceTo(min) * 0.5, 2),
    };
  }
  const box = mesh.getBoundingBox(true);
  return {
    center: box.getCenter(new THREE.Vector3()),
    radius: Math.max(box.getSize(new THREE.Vector3()).length() * 0.5, 2),
  };
}

async function mountSplatViewer(container, urls, options) {
  const status = document.createElement("div");
  status.className = "load-status";
  container.appendChild(status);
  setStatus(status, "Loading Gaussians…");

  const scene = options.scene ? `&scene=${encodeURIComponent(options.scene)}` : "";
  const iframe = document.createElement("iframe");
  iframe.className = "splat-frame";
  iframe.title = "Gaussian splat";
  iframe.allow = "autoplay";
  iframe.tabIndex = 0;
  iframe.src = `/splat-viewer/index.html?v=22&url=${encodeURIComponent(urls.splat)}${scene}`;
  iframe.addEventListener("load", () => {
    setStatus(status, "");
    iframe.focus();
    if (options.onReady) options.onReady();
  });
  iframe.addEventListener("error", () => {
    setStatus(status, "Gaussian viewer failed to start.", true);
  });
  container.appendChild(iframe);

  const controlKeys = new Set([
    "KeyW",
    "KeyA",
    "KeyS",
    "KeyD",
    "KeyQ",
    "KeyE",
    "KeyR",
    "KeyF",
    "KeyC",
    "Space",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "PageUp",
    "PageDown",
    "KeyI",
    "KeyK",
    "KeyJ",
    "KeyO",
  ]);
  const forwardKey = (e) => {
    if (!controlKeys.has(e.code)) return;
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA") return;
    iframe.contentWindow?.postMessage({ type: "key", code: e.code, down: e.type === "keydown" }, "*");
    iframe.focus();
    e.preventDefault();
  };
  window.addEventListener("keydown", forwardKey);
  window.addEventListener("keyup", forwardKey);
  container.addEventListener("pointerdown", () => iframe.focus());

  function post(type) {
    iframe.contentWindow?.postMessage({ type }, "*");
  }

  return {
    async setMode(mode) {
      if (mode === "mesh") {
        setStatus(status, "No triangle mesh in this sample. Stay on Gaussians — that is the 3D model.", true);
        iframe.style.visibility = "visible";
        return;
      }
      iframe.style.visibility = "visible";
      setStatus(status, "");
    },
    setConfidence() {},
    setMeasure() {},
    setFlyMode() {},
    levelView() {
      post("level");
    },
    resetView() {
      post("reset");
    },
    dispose() {
      window.removeEventListener("keydown", forwardKey);
      window.removeEventListener("keyup", forwardKey);
      iframe.remove();
      status.remove();
    },
  };
}

async function mountMeshViewer(container, urls, options) {
  const yUp = Boolean(options.yUp);
  const { scene, camera, renderer, controls, status, ro } = createStage(container, {
    yUp,
    antialias: true,
  });

  scene.add(new THREE.AmbientLight(0xffffff, 0.45));
  scene.add(new THREE.HemisphereLight(0xf4f1e8, 0x24301c, 0.95));
  const sun = new THREE.DirectionalLight(0xfff4e0, 1.15);
  sun.position.set(45, 100, 55);
  scene.add(sun);

  const grid = new THREE.GridHelper(120, 24, 0x2a3320, 0x1a1e18);
  if (!yUp) grid.rotation.x = Math.PI / 2;
  scene.add(grid);

  setStatus(status, "Loading reconstruction…");
  const loader = new PLYLoader();
  const cloudGeom = await loader.loadAsync(urls.pointcloud);
  const pos = cloudGeom.getAttribute("position");
  const robust = robustPointBounds(pos);
  cloudGeom.translate(-robust.center.x, -robust.center.y, -robust.center.z);
  cloudGeom.computeBoundingBox();
  if (!cloudGeom.attributes.normal) cloudGeom.computeVertexNormals();

  const colors = cloudGeom.attributes.color;
  const baseColors = colors ? colors.array.slice() : null;
  applyConfidence(cloudGeom, options.confidence, baseColors);
  const pointCount = pos?.count || 0;
  const previewSparse = Boolean(options.preview) || pointCount < 80000;
  const pointSize = Math.max(robust.radius * (previewSparse ? 0.016 : 0.009), 0.03);

  const points = new THREE.Points(
    cloudGeom,
    new THREE.PointsMaterial({
      size: pointSize,
      vertexColors: Boolean(cloudGeom.attributes.color),
      sizeAttenuation: true,
    })
  );
  scene.add(points);

  let mesh = null;
  if (urls.mesh) {
    try {
      const meshGeom = await loader.loadAsync(urls.mesh);
      meshGeom.translate(-robust.center.x, -robust.center.y, -robust.center.z);
      meshGeom.computeVertexNormals();
      mesh = new THREE.Mesh(
        meshGeom,
        new THREE.MeshLambertMaterial({
          vertexColors: Boolean(meshGeom.attributes.color),
          side: THREE.DoubleSide,
          polygonOffset: true,
          polygonOffsetFactor: 1,
          polygonOffsetUnits: 1,
        })
      );
      mesh.visible = options.initialMode === "mesh";
      scene.add(mesh);
    } catch {
      mesh = null;
    }
  }

  points.visible = options.initialMode !== "mesh" || !mesh;
  const radius = Math.max(robust.radius, 1.6);
  if (yUp) camera.position.set(radius * 0.55, radius * 0.35, radius * 0.7);
  else camera.position.set(radius * 0.85, radius * 0.28, radius * 0.72);
  controls.target.set(0, 0, 0);
  controls.update();
  setStatus(status, "");

  const interaction = bindFlyAndMeasure({
    renderer,
    camera,
    controls,
    scene,
    options,
    yUp,
    getRadius: () => radius,
    getPickTargets() {
      const targets = [];
      if (mesh && mesh.visible) targets.push(mesh);
      if (points.visible) targets.push(points);
      return targets;
    },
    status,
  });

  let raf = 0;
  function loop() {
    controls.update();
    renderer.render(scene, camera);
    raf = requestAnimationFrame(loop);
  }
  loop();

  return {
    setMode(mode) {
      points.visible = mode === "points" || (mode === "splats" && !mesh);
      if (mesh) mesh.visible = mode === "mesh";
      if (mode === "splats") {
        points.visible = true;
        points.material.size = pointSize * 1.35;
      } else {
        points.material.size = pointSize;
      }
    },
    setConfidence(on) {
      applyConfidence(cloudGeom, on, baseColors);
    },
    setMeasure: interaction.setMeasure,
    setFlyMode: interaction.setFlyMode,
    levelView() {},
    resetView() {
      if (yUp) camera.position.set(radius * 0.55, radius * 0.35, radius * 0.7);
      else camera.position.set(radius * 0.85, radius * 0.28, radius * 0.72);
      controls.target.set(0, 0, 0);
    },
    dispose() {
      cancelAnimationFrame(raf);
      ro.disconnect();
      interaction.dispose();
      renderer.dispose();
      container.querySelectorAll("canvas, .load-status").forEach((el) => el.remove());
    },
  };
}

function applyConfidence(geometry, on, baseColors) {
  if (!baseColors || !geometry.attributes.confidence || !geometry.attributes.color) return;
  const conf = geometry.attributes.confidence.array;
  const arr = geometry.attributes.color.array;
  for (let i = 0; i < conf.length; i++) {
    if (on) {
      const c = conf[i];
      arr[i * 3] = 1 - c;
      arr[i * 3 + 1] = c;
      arr[i * 3 + 2] = 0.15;
    } else {
      arr[i * 3] = baseColors[i * 3];
      arr[i * 3 + 1] = baseColors[i * 3 + 1];
      arr[i * 3 + 2] = baseColors[i * 3 + 2];
    }
  }
  geometry.attributes.color.needsUpdate = true;
}
