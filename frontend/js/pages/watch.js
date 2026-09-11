export function renderWatch(root) {
  root.innerHTML = `
    <div class="page">
      <p class="home-label">Sample video</p>
      <h1>Ignatius orbit.</h1>
      <p class="lede">
        A slow circle around the statue. Keep the subject in the middle of the frame
        the whole way. This is the kind of video to upload — not a one-way cinematic pass.
      </p>
      <div class="watch-frame">
        <video
          src="/sample/ignatius-web.mp4"
          poster="/sample/ignatius-poster.jpg"
          controls
          playsinline
          preload="metadata"
        ></video>
      </div>
      <div class="meta-row">
        <span class="tag">720p · 30 fps</span>
        <span class="tag">Ignatius garden</span>
        <span class="tag">~4 min · 25 MB</span>
      </div>
      <div class="cover-acts">
        <a class="act fill" href="/sample/ignatius-web.mp4" download="ignatius-orbit.mp4">Download video</a>
        <a class="act line" href="#/upload">Upload a video</a>
        <a class="act text" href="#/examples">Open examples</a>
      </div>
    </div>
  `;
}
