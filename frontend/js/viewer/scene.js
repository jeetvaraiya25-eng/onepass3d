import * as THREE from "three";
import { TrackballControls } from "three/addons/controls/TrackballControls.js";
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

  const controls = new TrackballControls(camera, renderer.domElement);
  controls.rotateSpeed = 3.2;
  controls.zoomSpeed = 1.35;
  controls.panSpeed = 0.85;
  controls.dynamicDampingFactor = 0.18;
  renderer.domElement.style.touchAction = "none";

  const status = document.createElement("div");
  status.className = "load-status";
  container.appendChild(status);

  function resize() {
    const w = container.clientWidth;
    const h = container.clientHeight;
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
    controls.handleResize();
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

function worldAxes(up) {
  const worldUp = (up && up.lengthSq() > 0.01 ? up.clone() : new THREE.Vector3(0, 1, 0)).normalize();
  const east = new THREE.Vector3(0, 1, 0);
  if (Math.abs(east.dot(worldUp)) > 0.85) east.set(1, 0, 0);
  east.cross(worldUp).normalize();
  const north = new THREE.Vector3().crossVectors(worldUp, east).normalize();
  return { worldUp, east, north };
}

function forwardFromAngles(yaw, pitch, up) {
  const { worldUp, east, north } = worldAxes(up);
  const cp = Math.cos(pitch);
  return north
    .multiplyScalar(Math.cos(yaw) * cp)
    .addScaledVector(east, Math.sin(yaw) * cp)
    .addScaledVector(worldUp, Math.sin(pitch))
    .normalize();
}

function anglesFromForward(fwd, up) {
  const { worldUp, east, north } = worldAxes(up);
  const dir = fwd.clone().normalize();
  const pitch = Math.asin(Math.max(-1, Math.min(1, dir.dot(worldUp))));
  const flat = dir.clone().addScaledVector(worldUp, -dir.dot(worldUp));
  if (flat.lengthSq() < 1e-8) return { yaw: 0, pitch };
  flat.normalize();
  return { yaw: Math.atan2(flat.dot(east), flat.dot(north)), pitch };
}

function bindFlyAndMeasure({ renderer, camera, controls, scene, options, yUp, getPickTargets, getRadius, getUp, status }) {
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
  let looking = false;
  let yaw = 0;
  let pitch = 0;
  const lookUp = new THREE.Vector3(0, yUp ? 1 : 0, yUp ? 0 : 1);
  const held = new Set();
  const WALK_KEYS = new Set(["KeyW", "KeyA", "KeyS", "KeyD", "ArrowUp", "ArrowDown"]);

  function currentUp() {
    const fromScene = getUp?.();
    if (fromScene && fromScene.lengthSq() > 0.01) return fromScene.clone().normalize();
    return camera.up.clone().normalize();
  }

  function applyLook() {
    const fwd = forwardFromAngles(yaw, pitch, lookUp);
    const aim = camera.position.clone().add(fwd);
    camera.up.copy(lookUp);
    camera.lookAt(aim);
    controls.target.copy(aim);
  }

  function enterLook(hitPoint) {
    looking = true;
    controls.enabled = false;
    lookUp.copy(currentUp());
    const fwd = hitPoint.clone().sub(camera.position);
    if (fwd.lengthSq() < 1e-8) fwd.copy(camera.getWorldDirection(new THREE.Vector3()));
    const angles = anglesFromForward(fwd, lookUp);
    yaw = angles.yaw;
    pitch = angles.pitch;
    applyLook();
    renderer.domElement.style.cursor = "grab";
    if (options.onLook) options.onLook(hitPoint);
  }

  function resetLook() {
    looking = false;
    flying = false;
    controls.enabled = true;
    renderer.domElement.style.cursor = "pointer";
  }

  function standOff(hit) {
    const radius = getRadius();
    const dist = Math.min(Math.max(radius * 0.16, 2.8), radius * 0.38);
    const worldUp = currentUp();
    const fromCamera = camera.position.clone().sub(hit.point);
    if (fromCamera.lengthSq() < 1e-6) fromCamera.copy(worldUp);
    fromCamera.normalize();
    const pos = hit.point.clone().addScaledVector(fromCamera, dist);
    const alongUp = pos.clone().sub(hit.point).dot(worldUp);
    if (alongUp < dist * 0.28) pos.addScaledVector(worldUp, dist * 0.28 - alongUp);
    return pos;
  }

  function flyTo(hit) {
    const point = hit.point.clone();
    const startPos = camera.position.clone();
    const startTarget = controls.target.clone();
    const endPos = standOff(hit);
    flying = true;
    controls.enabled = false;
    const t0 = performance.now();
    function tick(now) {
      const u = Math.min(1, (now - t0) / 900);
      const e = 1 - Math.pow(1 - u, 3);
      camera.position.lerpVectors(startPos, endPos, e);
      controls.target.lerpVectors(startTarget, point, e);
      camera.lookAt(controls.target);
      if (u < 1) requestAnimationFrame(tick);
      else {
        flying = false;
        enterLook(point);
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
    return hits.length ? hits[0] : null;
  }

  function resetMeasure() {
    measure.picks = [];
    measure.distance = null;
    measure.markers.clear();
    measure.line = null;
    if (options.onMeasure) options.onMeasure(null);
  }

  function onPointerDown(event) {
    pointerDown = { x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY, looking };
    if (looking) renderer.domElement.style.cursor = "grabbing";
  }

  function onPointerMove(event) {
    if (!pointerDown || flying) return;
    if (!looking) return;
    const dx = event.clientX - pointerDown.x;
    const dy = event.clientY - pointerDown.y;
    pointerDown.x = event.clientX;
    pointerDown.y = event.clientY;
    yaw -= dx * 0.0045;
    pitch = Math.max(-1.35, Math.min(1.35, pitch - dy * 0.0045));
    applyLook();
  }

  function onPointerUp(event) {
    if (!pointerDown || flying) return;
    const dx = event.clientX - pointerDown.startX;
    const dy = event.clientY - pointerDown.startY;
    pointerDown = null;
    if (looking) renderer.domElement.style.cursor = "grab";
    if (dx * dx + dy * dy > 25) return;
    const hit = pick(event);
    if (!hit) return;
    if (measure.active) {
      const point = hit.point.clone();
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
    if (flyMode) flyTo(hit);
  }

  function onWheel(event) {
    if (!looking || flying) return;
    event.preventDefault();
    const fwd = forwardFromAngles(yaw, pitch, lookUp);
    const step = getRadius() * 0.035 * (event.deltaY > 0 ? -1 : 1);
    camera.position.addScaledVector(fwd, step);
    applyLook();
  }

  function typingInField() {
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
  }

  function walkAxes() {
    const worldUp = looking ? lookUp.clone().normalize() : currentUp();
    const look = looking
      ? forwardFromAngles(yaw, pitch, lookUp)
      : camera.getWorldDirection(new THREE.Vector3());
    const right = new THREE.Vector3().crossVectors(look, worldUp);
    if (right.lengthSq() < 1e-8) {
      right.copy(worldAxes(worldUp).east);
    } else {
      right.normalize();
    }
    const forward = new THREE.Vector3().crossVectors(worldUp, right).normalize();
    return { forward, right, worldUp };
  }

  function applyWalk(dx, dy, dz) {
    const step = Math.max(getRadius() * 0.018, 0.08);
    const { forward, right, worldUp } = walkAxes();
    const delta = new THREE.Vector3()
      .addScaledVector(right, dx * step)
      .addScaledVector(worldUp, dy * step)
      .addScaledVector(forward, dz * step);
    camera.position.add(delta);
    if (looking) applyLook();
    else controls.target.add(delta);
  }

  function onKeyDown(event) {
    if (!WALK_KEYS.has(event.code) || typingInField()) return;
    event.preventDefault();
    held.add(event.code);
  }

  function onKeyUp(event) {
    held.delete(event.code);
  }

  function onWindowBlur() {
    held.clear();
  }

  function tick() {
    if (flying || !held.size) return;
    let dx = 0;
    let dy = 0;
    let dz = 0;
    if (held.has("KeyD")) dx += 1;
    if (held.has("KeyA")) dx -= 1;
    if (held.has("KeyW")) dz += 1;
    if (held.has("KeyS")) dz -= 1;
    if (held.has("ArrowUp")) dy += 1;
    if (held.has("ArrowDown")) dy -= 1;
    if (dx && dz) {
      dx *= Math.SQRT1_2;
      dz *= Math.SQRT1_2;
    }
    if (dx || dy || dz) applyWalk(dx, dy, dz);
  }

  renderer.domElement.addEventListener("pointerdown", onPointerDown);
  renderer.domElement.addEventListener("pointermove", onPointerMove);
  renderer.domElement.addEventListener("pointerup", onPointerUp);
  renderer.domElement.addEventListener("wheel", onWheel, { passive: false });
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);
  window.addEventListener("blur", onWindowBlur);
  renderer.domElement.style.cursor = "pointer";
  renderer.domElement.tabIndex = 0;

  return {
    measure,
    resetMeasure,
    resetLook,
    isLooking() {
      return looking;
    },
    tick,
    setFlyMode(on) {
      flyMode = on;
      if (on) {
        measure.active = false;
        resetMeasure();
        if (!looking) renderer.domElement.style.cursor = "pointer";
      }
    },
    setMeasure(on) {
      measure.active = on;
      if (on) flyMode = false;
      if (!on) resetMeasure();
      renderer.domElement.style.cursor = on ? "crosshair" : looking ? "grab" : "pointer";
    },
    dispose() {
      held.clear();
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("wheel", onWheel);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onWindowBlur);
    },
    status,
  };
}

function robustPointBounds(pos, normals) {
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
    return { center: new THREE.Vector3(), radius: 8, up: new THREE.Vector3(0, 1, 0) };
  }
  const min = new THREE.Vector3(pct(xs, 0.06), pct(ys, 0.06), pct(zs, 0.06));
  const max = new THREE.Vector3(pct(xs, 0.94), pct(ys, 0.94), pct(zs, 0.94));
  const size = max.clone().sub(min);
  const up = new THREE.Vector3(0, 0, 1);
  if (size.y <= size.x && size.y <= size.z) up.set(0, 1, 0);
  else if (size.x <= size.y && size.x <= size.z) up.set(1, 0, 0);
  if (normals && normals.count) {
    let score = 0;
    const step = Math.max(1, Math.floor(normals.count / 12000));
    for (let i = 0; i < normals.count; i += step) {
      score += normals.getX(i) * up.x + normals.getY(i) * up.y + normals.getZ(i) * up.z;
    }
    if (score < 0) up.negate();
  }
  return {
    center: min.clone().add(max).multiplyScalar(0.5),
    radius: Math.max(max.distanceTo(min) * 0.55, 1.6),
    up,
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

async function readWithProgress(res, total, onProgress) {
  const reader = res.body.getReader();
  const chunks = [];
  let loaded = 0;
  let lastPaint = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    loaded += value.byteLength;
    const now = performance.now();
    if (now - lastPaint > 120) {
      lastPaint = now;
      onProgress(loaded, total);
    }
  }
  onProgress(loaded, total || loaded);
  const out = new Uint8Array(loaded);
  let at = 0;
  for (const chunk of chunks) {
    out.set(chunk, at);
    at += chunk.byteLength;
  }
  return out.buffer;
}

async function loadGlbBuffer(url, onProgress) {
  const res = await fetch(url);
  const type = res.headers.get("content-type") || "";
  const length = res.headers.get("content-length") || "?";
  if (!res.ok) {
    throw new Error(`Model HTTP ${res.status} (${type}, ${length} bytes)`);
  }
  const buf = onProgress && res.body ? await readWithProgress(res, Number(length) || 0, onProgress) : await res.arrayBuffer();
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

function preparePhotogrammetryMaterial(mat, geometry, renderer) {
  const hasColor = Boolean(geometry?.attributes?.color);
  const hasMap = Boolean(mat.map);
  if (hasMap) {
    const tex = mat.map;
    const img = tex.image;
    const maxSize = Math.min(4096, renderer?.capabilities?.maxTextureSize || 4096);
    if (img && (img.width > maxSize || img.height > maxSize)) {
      const canvas = document.createElement("canvas");
      const scale = maxSize / Math.max(img.width, img.height);
      canvas.width = Math.max(1, Math.round(img.width * scale));
      canvas.height = Math.max(1, Math.round(img.height * scale));
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      tex.image = canvas;
    }
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.generateMipmaps = true;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.anisotropy = Math.min(8, renderer?.capabilities?.getMaxAnisotropy?.() || 1);
    tex.needsUpdate = true;
    mat.vertexColors = false;
    mat.color?.set(0xffffff);
    if ("metalness" in mat) mat.metalness = 0;
    if ("roughness" in mat) mat.roughness = 1;
    if ("envMapIntensity" in mat) mat.envMapIntensity = 0;
    mat.toneMapped = false;
  } else {
    mat.vertexColors = hasColor;
    if (!hasColor) mat.color?.set(0xc8c8c8);
  }
  mat.side = THREE.DoubleSide;
  mat.needsUpdate = true;
}

function aimLights(rig, up) {
  const n = (up && up.lengthSq() > 0.01 ? up.clone() : new THREE.Vector3(0, 1, 0)).normalize();
  const side = new THREE.Vector3(0, 1, 0);
  if (Math.abs(n.dot(side)) > 0.85) side.set(1, 0, 0);
  side.cross(n).normalize();
  if (rig.hemi) rig.hemi.position.copy(n);
  if (rig.sun) rig.sun.position.copy(n).multiplyScalar(90).addScaledVector(side, 45);
  if (rig.fill) rig.fill.position.copy(n).multiplyScalar(25).addScaledVector(side, -55);
}

function placeInspectCamera(camera, controls, radius, up) {
  const n = (up && up.lengthSq() > 0.01 ? up.clone() : new THREE.Vector3(0, 1, 0)).normalize();
  const side = new THREE.Vector3(0, 1, 0);
  if (Math.abs(n.dot(side)) > 0.85) side.set(1, 0, 0);
  side.cross(n).normalize();
  const along = new THREE.Vector3().crossVectors(n, side).normalize();
  camera.up.copy(n);
  camera.position
    .copy(n)
    .multiplyScalar(radius * 0.58)
    .addScaledVector(along, radius * 0.82)
    .addScaledVector(side, radius * 0.2);
  camera.near = Math.max(radius / 200, 0.01);
  camera.far = Math.max(radius * 40, 100);
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
  controls.target.set(0, 0, 0);
  controls.minDistance = Math.max(radius * 0.2, 0.05);
  controls.maxDistance = radius * 10;
  controls.update();
  if (controls.position0) {
    controls.position0.copy(camera.position);
    controls.target0.copy(controls.target);
    controls.up0.copy(camera.up);
  }
}

function frameObject(camera, controls, object) {
  let pos = null;
  let normals = null;
  object.traverse((obj) => {
    if (!pos && obj.isMesh && obj.geometry?.attributes?.position) {
      pos = obj.geometry.attributes.position;
      normals = obj.geometry.attributes.normal || null;
    }
  });
  let center;
  let radius;
  let up = camera.up.clone();
  if (pos && pos.count > 8) {
    const robust = robustPointBounds(pos, normals);
    center = robust.center;
    radius = robust.radius;
    up = robust.up;
  } else {
    const box = new THREE.Box3().setFromObject(object);
    if (box.isEmpty()) {
      throw new Error("GLB loaded but contained no visible mesh.");
    }
    center = box.getCenter(new THREE.Vector3());
    radius = Math.max(box.getSize(new THREE.Vector3()).length() * 0.5, 0.25);
  }
  object.position.copy(center).multiplyScalar(-1);
  placeInspectCamera(camera, controls, radius, up);
  return { radius, up };
}

async function mountGlbViewer(container, urls, options) {
  const yUp = options.yUp !== false;
  const { scene, camera, renderer, controls, status, ro } = createStage(container, {
    yUp,
    antialias: true,
  });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  const lights = {
    ambient: new THREE.AmbientLight(0xffffff, 1.05),
    hemi: new THREE.HemisphereLight(0xffffff, 0x2a2a2a, 0.45),
    sun: new THREE.DirectionalLight(0xffffff, 0.7),
    fill: new THREE.DirectionalLight(0xffffff, 0.22),
  };
  Object.values(lights).forEach((light) => scene.add(light));
  setStatus(status, "Loading 3D model…");

  let root;
  let radius;
  let framedUp = camera.up.clone();
  try {
    const buffer = await loadGlbBuffer(urls.glb, (loaded, total) => {
      const mbLoaded = Math.round(loaded / 1e6);
      const mbTotal = total ? Math.round(total / 1e6) : 0;
      setStatus(status, mbTotal ? `Loading 3D model… ${mbLoaded} / ${mbTotal} MB` : `Loading 3D model… ${mbLoaded} MB`);
    });
    setStatus(status, "Building the 3D model…");
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
        const next = mats.map((mat) => {
          const hasColor = Boolean(obj.geometry?.attributes?.color);
          if (hasColor) {
            return new THREE.MeshLambertMaterial({
              vertexColors: true,
              side: THREE.DoubleSide,
              polygonOffset: true,
              polygonOffsetFactor: 1,
              polygonOffsetUnits: 1,
            });
          }
          preparePhotogrammetryMaterial(mat, obj.geometry, renderer);
          if (mat.map) {
            mat.map = null;
            mat.vertexColors = false;
            mat.color?.set(0xc8c8c8);
          }
          return mat;
        });
        obj.material = Array.isArray(obj.material) ? next : next[0];
      }
    });
    if (meshCount === 0 || triCount < 3) {
      throw new Error("GLB parsed but it has no triangle mesh to show.");
    }
    scene.add(root);
    const framed = frameObject(camera, controls, root);
    radius = framed.radius;
    framedUp = framed.up;
    aimLights(lights, framed.up);
    setStatus(status, "");
    if (options.onReady) options.onReady();
  } catch (err) {
    setStatus(status, "The 3D view could not open. Reload the page to try again.", true);
    throw err;
  }

  const interaction = bindFlyAndMeasure({
    renderer,
    camera,
    controls,
    scene,
    options,
    yUp,
    getRadius: () => radius,
    getUp: () => framedUp,
    getPickTargets() {
      const targets = [];
      root?.traverse((obj) => {
        if (obj.isMesh) targets.push(obj);
      });
      return targets;
    },
    status,
  });

  let raf = 0;
  function loop() {
    if (!interaction.isLooking()) controls.update();
    interaction.tick();
    renderer.render(scene, camera);
    raf = requestAnimationFrame(loop);
  }
  loop();

  return {
    setMode() {},
    setConfidence() {},
    setMeasure: interaction.setMeasure,
    setFlyMode: interaction.setFlyMode,
    levelView() {},
    resetView() {
      interaction.resetLook();
      const framed = frameObject(camera, controls, root);
      framedUp = framed.up;
      aimLights(lights, framed.up);
    },
    dispose() {
      cancelAnimationFrame(raf);
      ro.disconnect();
      interaction.dispose();
      controls.dispose();
      renderer.dispose();
      container.querySelectorAll("canvas, .load-status").forEach((el) => el.remove());
    },
  };
}

async function mountSplatViewer(container, urls, options) {
  const status = document.createElement("div");
  status.className = "load-status";
  container.appendChild(status);
  setStatus(status, "Loading the scene…");

  const scene = options.scene ? `&scene=${encodeURIComponent(options.scene)}` : "";
  const iframe = document.createElement("iframe");
  iframe.className = "splat-frame";
  iframe.title = "3D scene";
  iframe.allow = "autoplay";
  iframe.tabIndex = 0;
  iframe.src = `/splat-viewer/index.html?v=23&url=${encodeURIComponent(urls.splat)}${scene}`;
  iframe.addEventListener("load", () => {
    setStatus(status, "");
    iframe.focus();
    if (options.onReady) options.onReady();
  });
  iframe.addEventListener("error", () => {
    setStatus(status, "The 3D view could not start. Reload the page to try again.", true);
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
        setStatus(status, "This example has no solid shape to show. Use the 3D view — that is the model.", true);
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

  const lights = {
    ambient: new THREE.AmbientLight(0xffffff, 0.8),
    hemi: new THREE.HemisphereLight(0xf4f1e8, 0x24301c, 0.5),
    sun: new THREE.DirectionalLight(0xfff4e0, 0.75),
    fill: new THREE.DirectionalLight(0xffffff, 0.2),
  };
  Object.values(lights).forEach((light) => scene.add(light));

  const grid = new THREE.GridHelper(120, 24, 0x2a3320, 0x1a1e18);
  scene.add(grid);

  setStatus(status, "Loading 3D model…");
  const loader = new PLYLoader();
  let mesh = null;
  let robust = { center: new THREE.Vector3(), radius: 8, up: new THREE.Vector3(0, 1, 0) };
  if (urls.mesh) {
    const meshGeom = await loader.loadAsync(urls.mesh);
    const mpos = meshGeom.getAttribute("position");
    meshGeom.computeVertexNormals();
    robust = robustPointBounds(mpos, meshGeom.getAttribute("normal"));
    meshGeom.translate(-robust.center.x, -robust.center.y, -robust.center.z);
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
    if (!cloudGeom.attributes.normal) cloudGeom.computeVertexNormals();
    if (!mesh) robust = robustPointBounds(pos, cloudGeom.getAttribute("normal"));
    cloudGeom.translate(-robust.center.x, -robust.center.y, -robust.center.z);
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
  const up = robust.up || new THREE.Vector3(0, yUp ? 1 : 0, yUp ? 0 : 1);
  grid.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), up.clone().normalize());
  aimLights(lights, up);
  placeInspectCamera(camera, controls, radius, up);
  setStatus(status, "");

  const interaction = bindFlyAndMeasure({
    renderer,
    camera,
    controls,
    scene,
    options,
    yUp,
    getRadius: () => radius,
    getUp: () => up,
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
    if (!interaction.isLooking()) controls.update();
    interaction.tick();
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
      interaction.resetLook();
      placeInspectCamera(camera, controls, radius, up);
    },
    dispose() {
      cancelAnimationFrame(raf);
      ro.disconnect();
      interaction.dispose();
      controls.dispose();
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
