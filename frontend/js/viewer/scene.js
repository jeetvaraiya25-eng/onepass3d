import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";

export async function mountViewer(container, urls, options) {
  if (urls.glb) return mountGlbViewer(container, urls, options);
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

async function loadGlbBuffer(url) {
  const res = await fetch(url, { cache: "no-store" });
  const type = res.headers.get("content-type") || "";
  const length = res.headers.get("content-length") || "?";
  console.info("[OnePass3D] GLB response", { url, status: res.status, type, length });
  if (!res.ok) {
    throw new Error(`Model HTTP ${res.status} (${type}, ${length} bytes)`);
  }
  const buf = await res.arrayBuffer();
  if (buf.byteLength < 20) {
    throw new Error(`Model file is empty (${buf.byteLength} bytes)`);
  }
  const head = new TextDecoder().decode(new Uint8Array(buf, 0, Math.min(8, buf.byteLength)));
  if (!head.startsWith("glTF")) {
    const peek = head.replace(/\s+/g, " ").slice(0, 48);
    throw new Error(`Server did not return a GLB (got ${type || "unknown type"} starting ${JSON.stringify(peek)})`);
  }
  return buf;
}

function preparePhotogrammetryMaterial(mat, geometry) {
  const hasColor = Boolean(geometry?.attributes?.color);
  const hasMap = Boolean(mat.map);
  if (hasMap) {
    mat.vertexColors = false;
    mat.color?.set(0xffffff);
    if ("metalness" in mat) mat.metalness = 0;
    if ("roughness" in mat) mat.roughness = 0.95;
    if ("envMapIntensity" in mat) mat.envMapIntensity = 0;
    mat.map.colorSpace = THREE.SRGBColorSpace;
    mat.map.anisotropy = 8;
    mat.map.needsUpdate = true;
  } else {
    mat.vertexColors = hasColor;
    if (!hasColor) mat.color?.set(0xc8c8c8);
  }
  mat.side = THREE.DoubleSide;
  mat.needsUpdate = true;
}

function frameObject(camera, controls, object) {
  const box = new THREE.Box3().setFromObject(object);
  if (box.isEmpty()) {
    throw new Error("GLB loaded but contained no visible mesh.");
  }
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const radius = Math.max(size.length() * 0.5, 0.25);
  object.position.sub(center);
  const dist = radius * 1.85;
  camera.near = Math.max(dist / 200, 0.01);
  camera.far = Math.max(dist * 40, 100);
  camera.position.set(dist * 0.72, dist * 0.42, dist * 0.78);
  camera.lookAt(0, 0, 0);
  controls.target.set(0, 0, 0);
  camera.updateProjectionMatrix();
  controls.update();
  return { radius };
}

async function mountGlbViewer(container, urls, options) {
  const yUp = options.yUp !== false;
  const { scene, camera, renderer, controls, status, ro } = createStage(container, {
    yUp,
    antialias: true,
  });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  scene.add(new THREE.AmbientLight(0xffffff, 1.2));
  scene.add(new THREE.HemisphereLight(0xffffff, 0x3a3a3a, 0.7));
  const sun = new THREE.DirectionalLight(0xffffff, 1.15);
  sun.position.set(40, 80, 50);
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0xffffff, 0.45);
  fill.position.set(-50, 20, -30);
  scene.add(fill);
  setStatus(status, "Loading 3D model…");

  let root;
  let radius;
  try {
    console.info("[OnePass3D] requesting GLB", urls.glb);
    const buffer = await loadGlbBuffer(urls.glb);
    console.info("[OnePass3D] GLB bytes", buffer.byteLength);
    const loader = new GLTFLoader();
    const resourcePath = new URL(".", new URL(urls.glb, window.location.href)).href;
    const gltf = await loader.parseAsync(buffer, resourcePath);
    root = gltf.scene;
    let meshCount = 0;
    let triCount = 0;
    root.traverse((obj) => {
      if (obj.isPoints && !obj.isMesh) return;
      if (!obj.isMesh) return;
      const pos = obj.geometry?.attributes?.position;
      const idx = obj.geometry?.index;
      if (!pos || pos.count < 3) return;
      meshCount += 1;
      triCount += idx ? idx.count / 3 : pos.count / 3;
      obj.frustumCulled = false;
      if (obj.material) {
        const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        mats.forEach((mat) => preparePhotogrammetryMaterial(mat, obj.geometry));
      }
    });
    console.info("[OnePass3D] GLB meshes", { meshCount, triCount });
    if (meshCount === 0 || triCount < 3) {
      throw new Error("GLB parsed but it has no triangle mesh to show.");
    }
    scene.add(root);
    const framed = frameObject(camera, controls, root);
    radius = framed.radius;
    setStatus(status, "");
    if (options.onReady) options.onReady();
  } catch (err) {
    const message = err?.message || String(err);
    setStatus(status, `Viewer failed: ${message}`, true);
    throw err;
  }

  let raf = 0;
  function loop() {
    controls.update();
    renderer.render(scene, camera);
    raf = requestAnimationFrame(loop);
  }
  loop();

  return {
    setMode() {},
    setConfidence() {},
    setMeasure() {},
    setFlyMode() {},
    levelView() {},
    resetView() {
      frameObject(camera, controls, root);
    },
    dispose() {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.dispose();
      container.querySelectorAll("canvas, .load-status").forEach((el) => el.remove());
    },
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

  setStatus(status, "Loading 3D model…");
  const loader = new PLYLoader();
  let mesh = null;
  let robust = { center: new THREE.Vector3(), radius: 8 };
  if (urls.mesh) {
    const meshGeom = await loader.loadAsync(urls.mesh);
    const mpos = meshGeom.getAttribute("position");
    robust = robustPointBounds(mpos);
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
    mesh.visible = true;
    scene.add(mesh);
  }

  let points = null;
  let pointSize = 0.05;
  if (urls.pointcloud && options.initialMode !== "mesh") {
    const cloudGeom = await loader.loadAsync(urls.pointcloud);
    const pos = cloudGeom.getAttribute("position");
    if (!mesh) robust = robustPointBounds(pos);
    cloudGeom.translate(-robust.center.x, -robust.center.y, -robust.center.z);
    if (!cloudGeom.attributes.normal) cloudGeom.computeVertexNormals();
    const colors = cloudGeom.attributes.color;
    const baseColors = colors ? colors.array.slice() : null;
    applyConfidence(cloudGeom, options.confidence, baseColors);
    const pointCount = pos?.count || 0;
    const previewSparse = Boolean(options.preview) || pointCount < 80000;
    pointSize = Math.max(robust.radius * (previewSparse ? 0.016 : 0.009), 0.03);
    points = new THREE.Points(
      cloudGeom,
      new THREE.PointsMaterial({
        size: pointSize,
        vertexColors: Boolean(cloudGeom.attributes.color),
        sizeAttenuation: true,
      })
    );
    points.visible = !mesh;
    scene.add(points);
  }
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
      if (points && points.visible) targets.push(points);
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
      if (mesh) mesh.visible = mode === "mesh" || !points;
      if (points) {
        points.visible = mode === "points" || (mode === "splats" && !mesh);
        points.material.size = mode === "splats" ? pointSize * 1.35 : pointSize;
      }
    },
    setConfidence() {},
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
