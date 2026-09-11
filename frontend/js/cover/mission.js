import * as THREE from "three";

const FRAME_CAP = 180;

function reduceMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function pad(n, width = 3) {
  return String(n).padStart(width, "0");
}

function fieldGeometry() {
  const count = 16000;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    if (i < count * 0.72) {
      const a = Math.random() * Math.PI * 2;
      const r = Math.pow(Math.random(), 0.55) * 14;
      positions[i * 3] = Math.cos(a) * r * 1.4;
      positions[i * 3 + 1] = -1.35 + Math.random() * 0.18;
      positions[i * 3 + 2] = Math.sin(a) * r;
    } else {
      const u = Math.random();
      const v = Math.random();
      const theta = u * Math.PI * 2;
      const phi = Math.acos(2 * v - 1);
      const r = Math.cbrt(Math.random()) * 3.2;
      positions[i * 3] = 4.2 + Math.sin(phi) * Math.cos(theta) * r;
      positions[i * 3 + 1] = 0.35 + Math.cos(phi) * r * 0.7;
      positions[i * 3 + 2] = Math.sin(phi) * Math.sin(theta) * r;
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  return geo;
}

export function mountCover(stage, hud) {
  const still = reduceMotion();

  const fieldScene = new THREE.Scene();
  fieldScene.background = new THREE.Color(0x070708);
  fieldScene.fog = new THREE.Fog(0x070708, 6, 22);
  const fieldCam = new THREE.PerspectiveCamera(42, 1, 0.2, 50);
  fieldCam.position.set(0.2, 1.1, 8.4);
  const fieldRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
  fieldRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
  stage.appendChild(fieldRenderer.domElement);
  const field = new THREE.Points(
    fieldGeometry(),
    new THREE.PointsMaterial({
      color: 0xd8dde6,
      size: 0.026,
      transparent: true,
      opacity: 0.7,
      depthWrite: false,
      sizeAttenuation: true,
    }),
  );
  fieldScene.add(field);

  const els = {
    frames: hud?.querySelector("[data-cover-frames]"),
    clock: hud?.querySelector("[data-cover-clock]"),
  };

  let frames = 42;
  let elapsed = 0;
  let nextShot = 1.2;
  let raf = 0;
  let last = performance.now();
  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };

  function writeHud() {
    if (els.frames) els.frames.textContent = `${pad(frames)} / ${FRAME_CAP}`;
    if (els.clock) {
      const t = Math.floor(elapsed);
      els.clock.textContent = `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
    }
  }

  function resize() {
    const w = stage.clientWidth;
    const h = stage.clientHeight;
    fieldCam.aspect = w / Math.max(h, 1);
    fieldCam.updateProjectionMatrix();
    fieldRenderer.setSize(w, h, false);
  }

  function renderOnce() {
    field.rotation.y = elapsed * 0.03 + pointer.x * 0.18;
    field.rotation.x = Math.sin(elapsed * 0.12) * 0.06 + pointer.y * 0.08;
    fieldCam.position.set(0.2 + pointer.x * 1.15, 1.1 + pointer.y * 0.55, 8.4);
    fieldCam.lookAt(pointer.x * 0.45, pointer.y * 0.2, 0);
    fieldRenderer.render(fieldScene, fieldCam);
    writeHud();
  }

  function tick(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    elapsed += dt;
    if (elapsed >= nextShot) {
      frames = (frames % FRAME_CAP) + 1;
      nextShot = elapsed + 1.15;
    }
    pointer.x += (pointer.tx - pointer.x) * 0.07;
    pointer.y += (pointer.ty - pointer.y) * 0.07;
    renderOnce();
    raf = requestAnimationFrame(tick);
  }

  function onPointerMove(event) {
    const r = stage.getBoundingClientRect();
    if (!r.width || !r.height) return;
    pointer.tx = THREE.MathUtils.clamp(((event.clientX - r.left) / r.width - 0.5) * 2, -0.92, 0.92);
    pointer.ty = THREE.MathUtils.clamp((0.5 - (event.clientY - r.top) / r.height) * 2, -0.85, 0.85);
  }

  const ro = new ResizeObserver(resize);
  ro.observe(stage);
  resize();
  renderOnce();
  window.addEventListener("pointermove", onPointerMove, { passive: true });
  if (!still) raf = requestAnimationFrame(tick);

  const onVis = () => {
    if (still) return;
    if (document.hidden) {
      cancelAnimationFrame(raf);
      raf = 0;
    } else if (!raf) {
      last = performance.now();
      raf = requestAnimationFrame(tick);
    }
  };
  document.addEventListener("visibilitychange", onVis);

  return () => {
    cancelAnimationFrame(raf);
    document.removeEventListener("visibilitychange", onVis);
    window.removeEventListener("pointermove", onPointerMove);
    ro.disconnect();
    field.geometry.dispose();
    field.material.dispose();
    fieldRenderer.dispose();
    fieldRenderer.domElement.remove();
    fieldScene.traverse((obj) => {
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material) {
        const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        mats.forEach((m) => m.dispose());
      }
    });
  };
}
