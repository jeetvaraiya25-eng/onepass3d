from __future__ import annotations

import shutil
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

from backend.app.config import ROOT_DIR


SAMPLE_DIR = ROOT_DIR / "data" / "sample"
HF = "https://huggingface.co/cakewalk/splat-data/resolve/main"

SCENES: dict[str, dict] = {
    "train": {
        "id": "train",
        "name": "Train station",
        "job_name": "Train station example",
        "filename": "train.splat",
        "url": f"{HF}/train.splat",
        "gaussians": 1_026_508,
        "blurb": "Photographs of a train engine parked inside a shed.",
        "source": "Inria 3D Gaussian Splatting — train scene (real photographs)",
    },
    "truck": {
        "id": "truck",
        "name": "Truck",
        "job_name": "Truck example",
        "filename": "truck.splat",
        "url": f"{HF}/truck.splat",
        "gaussians": 2_541_226,
        "blurb": "A truck outdoors with trees behind it.",
        "source": "Inria 3D Gaussian Splatting — Tanks and Temples truck",
    },
    "room": {
        "id": "room",
        "name": "Room",
        "job_name": "Room example",
        "filename": "room.splat",
        "url": f"{HF}/room.splat",
        "gaussians": 1_593_376,
        "blurb": "A furnished room, filmed all the way around.",
        "source": "Inria 3D Gaussian Splatting — Mip-NeRF 360 room",
    },
    "plush": {
        "id": "plush",
        "name": "Plush",
        "job_name": "Plush toy example",
        "filename": "plush.splat",
        "url": f"{HF}/plush.splat",
        "gaussians": 281_498,
        "blurb": "A small soft toy. This one opens the fastest.",
        "source": "Inria 3D Gaussian Splatting — plush object",
    },
}

SAMPLE_SPLAT = SAMPLE_DIR / "train.splat"
DEFAULT_SCENE = "train"


def scene_is_served(scene_id: str) -> bool:
    """True when a browser asking for /sample/<scene>.splat will actually get a file."""
    from backend.app.config import FRONTEND_DIR

    scene = _scene(scene_id)
    for path in (FRONTEND_DIR / "sample" / scene["filename"], SAMPLE_DIR / scene["filename"]):
        if path.exists() and path.is_file() and path.stat().st_size > 1_000_000:
            return True
    return False


def list_scenes() -> list[dict]:
    return [
        {
            "id": scene["id"],
            "name": scene["name"],
            "job_name": scene["job_name"],
            "blurb": scene["blurb"],
            "gaussians": scene["gaussians"],
            "ready": scene_is_served(scene["id"]),
        }
        for scene in SCENES.values()
    ]


def splat_path(scene_id: str) -> Path:
    scene = _scene(scene_id)
    return SAMPLE_DIR / scene["filename"]


def _scene(scene_id: str | None) -> dict:
    key = (scene_id or DEFAULT_SCENE).strip().lower()
    if key not in SCENES:
        known = ", ".join(SCENES)
        raise KeyError(f"Unknown sample scene '{scene_id}'. Try: {known}")
    return SCENES[key]


def ensure_sample_splat(scene_id: str = DEFAULT_SCENE) -> Path:
    scene = _scene(scene_id)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    dest = SAMPLE_DIR / scene["filename"]
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    _download(scene["url"], dest)
    if dest.stat().st_size < 1_000_000:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to download the {scene['name']} Gaussian splat sample.")
    return dest


def _write_lite_splat(src: Path, dest: Path, step: int = 4) -> None:
    raw = src.read_bytes()
    row = 32
    n = len(raw) // row
    out = bytearray((n // step) * row)
    j = 0
    for i in range(0, n, step):
        out[j : j + row] = raw[i * row : (i + 1) * row]
        j += row
    dest.write_bytes(out[:j])


def publish_frontend_samples() -> None:
    """Put example .splat files where the website can serve them."""
    from backend.app.config import FRONTEND_DIR

    public = FRONTEND_DIR / "sample"
    public.mkdir(parents=True, exist_ok=True)
    for key in SCENES:
        src = ensure_sample_splat(key)
        dest = public / src.name
        if dest.exists() and dest.stat().st_size > 1_000_000:
            continue
        dest.unlink(missing_ok=True)
        try:
            dest.hardlink_to(src)
        except OSError:
            shutil.copy2(src, dest)
    truck = public / "truck.splat"
    lite = public / "truck-lite.splat"
    if truck.exists() and (not lite.exists() or lite.stat().st_size < 1_000_000):
        _write_lite_splat(truck, lite)


def _download(url: str, dest: Path) -> None:
    req = Request(url, headers={"User-Agent": "OnePass3D/1.0"})
    with urlopen(req, timeout=180) as src, dest.open("wb") as out:
        shutil.copyfileobj(src, out)


def splat_count(path: Path) -> int:
    return path.stat().st_size // 32


def parse_splat(path: Path, max_points: int = 80_000) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    raw = path.read_bytes()
    n = len(raw) // 32
    if n < 16:
        raise RuntimeError("Splat file is empty or not in .splat format.")
    dt = np.dtype(
        [
            ("x", "<f4"),
            ("y", "<f4"),
            ("z", "<f4"),
            ("sx", "<f4"),
            ("sy", "<f4"),
            ("sz", "<f4"),
            ("r", "u1"),
            ("g", "u1"),
            ("b", "u1"),
            ("a", "u1"),
            ("rot0", "u1"),
            ("rot1", "u1"),
            ("rot2", "u1"),
            ("rot3", "u1"),
        ]
    )
    rec = np.frombuffer(raw[: n * 32], dtype=dt)
    step = max(1, n // max_points)
    rec = rec[::step]
    xyz = np.column_stack([rec["x"], rec["y"], rec["z"]]).astype(np.float64)
    rgb = np.column_stack([rec["r"], rec["g"], rec["b"]]).astype(np.uint8)
    conf = np.clip(rec["a"].astype(np.float32) / 255.0, 0.2, 1.0)
    finite = np.isfinite(xyz).all(axis=1)
    return xyz[finite], rgb[finite], conf[finite]


def build_photoreal_sample(scene_id: str = DEFAULT_SCENE) -> dict:
    scene = _scene(scene_id)
    splat = ensure_sample_splat(scene["id"])
    xyz, rgb, conf = parse_splat(splat)
    n = splat_count(splat)
    return {
        "splat_path": splat,
        "xyz": xyz,
        "rgb": rgb,
        "conf": conf,
        "splat_count": n,
        "meta": {
            "metric": False,
            "demo": True,
            "photoreal": True,
            "scene": scene["id"],
            "source": scene["source"],
            "note": (
                f"Real 3D Gaussian Splatting trained on photographs ({scene['name']}, "
                f"{n:,} Gaussians). This is the photoreal 3D model — use the Gaussians view. "
                "Training the same quality from your drone video needs COLMAP + 3DGS on an NVIDIA GPU."
            ),
        },
    }


def copy_splat_to_job(output_dir: Path, splat_path: Path) -> Path:
    dest = output_dir / "scene.splat"
    dest.unlink(missing_ok=True)
    try:
        dest.hardlink_to(splat_path)
    except OSError:
        shutil.copy2(splat_path, dest)
    return dest
