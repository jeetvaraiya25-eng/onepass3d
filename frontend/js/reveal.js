const SELECTOR = [
  ".chip",
  "h1",
  ".lede",
  ".actions",
  ".stats",
  ".section-head",
  ".card",
  ".table-wrap",
  ".drop",
  ".field",
  ".watch-frame",
  ".meta-row",
  ".empty",
  ".notice",
  ".chapter-head",
  ".library-row",
  ".build-step",
  ".door",
  ".index-row",
].join(",");

const STAGGER_MS = 70;
const MAX_DELAY_MS = 280;

let observer = null;
let scope = null;

function reduceMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function inViewport(el) {
  const r = el.getBoundingClientRect();
  return r.bottom > 32 && r.top < window.innerHeight - 16;
}

function revealVisible() {
  if (!scope) return;
  for (const el of scope.querySelectorAll(".reveal:not(.in)")) {
    if (inViewport(el)) el.classList.add("in");
  }
}

function onScrollOrResize() {
  revealVisible();
}

export function setupReveals(container) {
  teardownReveals();
  scope = container;
  if (!reduceMotion()) {
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) entry.target.classList.add("in");
        }
      },
      { threshold: 0, rootMargin: "0px 0px 0px 0px" }
    );
    window.addEventListener("scroll", onScrollOrResize, { passive: true });
    window.addEventListener("resize", onScrollOrResize);
  }
  scanReveals();
}

export function scanReveals() {
  if (!scope) return;
  const skipMotion = reduceMotion();
  for (const el of scope.querySelectorAll(SELECTOR)) {
    if (el.dataset.reveal || el.closest(".viewer-layout") || el.closest(".cover") || el.closest(".home-body") || el.closest(".index")) continue;
    el.dataset.reveal = "1";
    el.classList.add("reveal");
    const siblings = [...(el.parentElement?.children || [])].filter((n) => n.matches(SELECTOR));
    const delay = Math.min(siblings.indexOf(el) * STAGGER_MS, MAX_DELAY_MS);
    if (delay > 0) el.style.setProperty("--reveal-delay", `${delay}ms`);
    if (skipMotion || inViewport(el)) {
      el.classList.add("in");
    } else {
      el.classList.add("pending");
    }
    observer?.observe(el);
  }
  requestAnimationFrame(revealVisible);
}

export function teardownReveals() {
  if (observer) observer.disconnect();
  observer = null;
  scope = null;
  window.removeEventListener("scroll", onScrollOrResize);
  window.removeEventListener("resize", onScrollOrResize);
}
