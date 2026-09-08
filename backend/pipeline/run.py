from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from backend.app.config import MAX_WEB_POINTS, MIN_FRAMES
from backend.app.services.storage import job_dir, update_job
from backend.app.services.telemetry import find_telemetry_file, parse_telemetry
from backend.pipeline.demo.real_splat import DEFAULT_SCENE, build_photoreal_sample, copy_splat_to_job
from backend.pipeline.export.mesh import export_mesh
from backend.pipeline.export.ply import write_ascii_ply
from backend.pipeline.export.pointcloud import export_pointcloud
from backend.pipeline.export.preview import write_preview
from backend.pipeline.export.report import write_report
from backend.pipeline.filters.dynamic import motion_masks
from backend.pipeline.geo.align import align_to_gps, transform_points
from backend.pipeline.ingest.quality import select_keyframes
from backend.pipeline.ingest.video import collect_source_frames, save_frames
from backend.pipeline.reconstruct.pointcloud import (
    downsample_points,
    filter_outliers,
    triangulate_semidense,
    triangulate_sparse,
)
from backend.pipeline.reconstruct.poses import estimate_poses


ProgressFn = Callable[[str, int, str], None]


def _progress(job_id: str, stage: str, percent: int, message: str) -> None:
    update_job(
        job_id,
        status="running",
        progress={"stage": stage, "percent": percent, "message": message},
        log=message,
    )


def run_job(job_id: str) -> None:
    record = update_job(job_id, status="running")
    if record.get("is_demo"):
        _run_demo(job_id)
        return
    _run_reconstruction(job_id)


def _run_demo(job_id: str) -> None:
    record = update_job(job_id)
    scene_id = record.get("demo_scene") or DEFAULT_SCENE
    _progress(job_id, "reconstructing", 15, f"Loading photoreal 3D Gaussian Splatting scene ({scene_id})")
    scene = build_photoreal_sample(scene_id)
    xyz, rgb, conf = scene["xyz"], scene["rgb"], scene["conf"]
    out = job_dir(job_id) / "output"
    _progress(job_id, "exporting", 55, "Writing Gaussian splat and point cloud")
    copy_splat_to_job(out, scene["splat_path"])
    write_ascii_ply(out / "pointcloud.ply", xyz, rgb=rgb, confidence=conf)
    export_pointcloud(out, xyz, rgb, conf)
    write_preview(out, xyz, rgb, [])
    n_splats = int(scene["splat_count"])
    report = {
        "job_id": job_id,
        "demo": True,
        "photoreal": True,
        "point_count": n_splats,
        "triangle_count": 0,
        "metric": False,
        "units": "scene units",
        "has_gps": False,
        "geo": scene["meta"],
        "confidence": {
            "mean": float(conf.mean()) if len(conf) else 0.0,
            "note": scene["meta"]["note"],
        },
        "thumbs": [],
        "files": {
            "splat": "scene.splat",
            "pointcloud": "pointcloud.ply",
            "gaussians": "scene.splat",
            "preview": "preview.jpg",
            "report": "report.json",
        },
    }
    write_report(out, report)
    update_job(
        job_id,
        status="done",
        has_gps=False,
        metric=False,
        frame_count=0,
        point_count=n_splats,
        triangle_count=0,
        result=report,
        progress={"stage": "done", "percent": 100, "message": "Photoreal Gaussian splat ready"},
        log=f"Real 3DGS scene loaded: {scene_id}",
    )


def _run_reconstruction(job_id: str) -> None:
    root = job_dir(job_id)
    input_dir = root / "input"
    work_frames = root / "work" / "frames"
    output_dir = root / "output"

    _progress(job_id, "ingesting", 8, "Reading video / photos")

    def _ingest_progress(kept: int, target: int, name: str) -> None:
        pct = 8 + int(10 * kept / max(target, 1))
        _progress(job_id, "ingesting", pct, f"Reading {name} — {kept} of {target} frames")

    raw_frames = collect_source_frames(input_dir, on_progress=_ingest_progress)
    _progress(job_id, "ingesting", 18, f"Collected {len(raw_frames)} candidate frames")

    frames, kept_idx = select_keyframes(raw_frames)
    if len(frames) < MIN_FRAMES:
        raise RuntimeError(
            f"Need at least {MIN_FRAMES} sharp, distinct frames. Got {len(frames)}. "
            "Upload a longer single-pass clip or more photos."
        )
    save_frames(frames, work_frames)
    thumbs = _save_thumbs(frames, output_dir / "thumbs")
    update_job(job_id, frame_count=len(frames))
    _progress(job_id, "ingesting", 28, f"Kept {len(frames)} keyframes")

    telemetry_path = find_telemetry_file(input_dir)
    telemetry = parse_telemetry(telemetry_path) if telemetry_path else []
    has_gps = len(telemetry) >= 2
    update_job(job_id, has_gps=has_gps)
    if has_gps:
        _progress(job_id, "ingesting", 32, f"Parsed {len(telemetry)} GPS samples from {telemetry_path.name}")
    else:
        _progress(job_id, "ingesting", 32, "No GPS file found — reconstruction will be in relative units")

    _progress(job_id, "reconstructing", 40, "Estimating camera poses from the single pass")
    pose, pair_data = estimate_poses(frames)
    vo_centers = pose.centers.copy()

    _progress(job_id, "reconstructing", 52, "Filtering moving objects")
    masks = motion_masks(frames)

    _progress(job_id, "reconstructing", 60, "Triangulating sparse + semi-dense points")
    xyz_s, rgb_s, conf_s = triangulate_sparse(pose, pair_data, frames)
    xyz_d, rgb_d, conf_d = triangulate_semidense(frames, pose, masks, grid=96, spans=(1, 2))
    xyz, rgb, conf = _merge_clouds(xyz_s, rgb_s, conf_s, xyz_d, rgb_d, conf_d)
    if len(xyz) < 40:
        raise RuntimeError(
            "Not enough 3D points. Use a slower drone pass with overlapping frames, "
            "less motion blur, and more than 5 photos of the same area."
        )
    xyz, rgb, conf = filter_outliers(xyz, rgb, conf)
    xyz, rgb, conf = downsample_points(xyz, rgb, conf, max_points=MAX_WEB_POINTS)
    _progress(job_id, "reconstructing", 72, f"Point cloud has {len(xyz)} points")

    geo_meta = {"metric": False, "scale": 1.0}
    aligned_centers = vo_centers
    if has_gps:
        _progress(job_id, "georeferencing", 80, "Locking scale and location to GPS")
        aligned_centers, gps_meta = align_to_gps(vo_centers, telemetry)
        xyz, sim_meta = transform_points(xyz, vo_centers, aligned_centers)
        geo_meta = {**gps_meta, **sim_meta}
    else:
        _progress(job_id, "georeferencing", 80, "Skipping GPS lock")

    _progress(job_id, "exporting", 88, "Writing point cloud, mesh, and preview")
    export_pointcloud(output_dir, xyz, rgb, conf)
    span = np.ptp(xyz, axis=0)
    terrain_like = float(span[2]) < max(float(span[0]), float(span[1]), 1e-6) * 0.9
    files = {
        "pointcloud": "pointcloud.ply",
        "gaussians": "gaussians.ply",
        "splat": "scene.splat",
        "obj": "mesh.obj",
        "preview": "preview.jpg",
        "report": "report.json",
    }
    if terrain_like:
        tri_count, _, _ = export_mesh(output_dir, xyz, rgb, conf)
        files["mesh"] = "mesh.ply"
    else:
        # Vertical objects (chimney, facade orbit) make a spiked heightfield — skip it.
        tri_count = 0
    write_preview(output_dir, xyz, rgb, frames)
    trajectory = {
        "vo": vo_centers.tolist(),
        "aligned": aligned_centers.tolist(),
        "keyframes": kept_idx,
    }
    (output_dir / "trajectory.json").write_text(
        __import__("json").dumps(trajectory), encoding="utf-8"
    )

    units = "meters" if geo_meta.get("metric") else "relative units"
    report = {
        "job_id": job_id,
        "demo": False,
        "point_count": int(len(xyz)),
        "triangle_count": int(tri_count),
        "frame_count": len(frames),
        "metric": bool(geo_meta.get("metric")),
        "units": units,
        "has_gps": has_gps,
        "geo": _jsonable(geo_meta),
        "thumbs": [p.name for p in thumbs],
        "confidence": {
            "mean": float(conf.mean()) if len(conf) else 0.0,
            "note": (
                "Dense CPU preview from your video — colored dots, not a trained 3DGS kitchen. "
                "Room / Train / Truck / Plush are GPU-trained models. This Mac cannot train that "
                "quality from one clip. Only surfaces visible in this pass are reconstructed."
            ),
            "preview": True,
        },
        "files": files,
    }
    write_report(output_dir, report)
    update_job(
        job_id,
        status="done",
        metric=bool(geo_meta.get("metric")),
        point_count=int(len(xyz)),
        triangle_count=int(tri_count),
        result=report,
        progress={"stage": "done", "percent": 100, "message": "Reconstruction complete"},
        log="Exports written",
    )


def _merge_clouds(*chunks):
    xyzs, rgbs, confs = [], [], []
    for i in range(0, len(chunks), 3):
        xyz, rgb, conf = chunks[i : i + 3]
        if len(xyz):
            xyzs.append(xyz)
            rgbs.append(rgb)
            confs.append(conf)
    if not xyzs:
        return (
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0, 3), dtype=np.uint8),
            np.zeros((0,), dtype=np.float32),
        )
    return np.concatenate(xyzs), np.concatenate(rgbs), np.concatenate(confs)


def _save_thumbs(frames: list[np.ndarray], folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, frame in enumerate(frames[:12]):
        h, w = frame.shape[:2]
        scale = 180 / h
        thumb = cv2.resize(frame, (int(w * scale), 180))
        path = folder / f"thumb_{i:02d}.jpg"
        cv2.imwrite(str(path), thumb)
        paths.append(path)
    return paths


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value
