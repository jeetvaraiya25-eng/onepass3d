export function renderWatch(root) {
  root.innerHTML = `
    <p class="chip">Sample capture</p>
    <h1>Chimney orbit</h1>
    <p class="lede">
      The licensed drone orbit you can use. It is a Point of Interest circle around a
      chimney — the same flight idea as the DJI Mini 4 Pro short, not a spherical 360
      camera.
    </p>
    <div class="watch-frame">
      <video src="/sample/drone_orbit.mp4" controls autoplay muted playsinline></video>
    </div>
    <div class="meta-row">
      <span class="tag">1080p · 60 fps</span>
      <span class="tag">Pexels licence</span>
      <span class="tag">Dimitar Germanov</span>
    </div>
    <div class="actions">
      <a class="btn primary" href="/sample/drone_orbit.mp4" download>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v12m0 0-4.5-4.5M12 16l4.5-4.5"/><path d="M4 19h16"/></svg>
        Download mp4
      </a>
      <a class="btn ghost" href="#/examples">Open photoreal 3D examples</a>
      <a class="btn ghost" href="#/upload">Upload this clip</a>
    </div>
    <p class="notice" style="margin-top:32px;max-width:1000px">
      <span>
        Uploading this video will not look like the train splat. That quality needs
        trained 3DGS on an NVIDIA GPU. Use
        <a href="#/examples">Train, Truck, Room, or Plush</a> for photoreal 3D.
      </span>
    </p>
  `;
}
