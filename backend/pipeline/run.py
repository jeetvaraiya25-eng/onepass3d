from __future__ import annotations

import shutil
from pathlib import Path

import cv2
import numpy as np

from backend.app.config import DENSE_BACKEND, MIN_FRAMES, RECONSTRUCTION_DEBUG, apply_job_quality
from backend.app.services.storage import job_dir, load_job, update_job, utc_now
from backend.pipeline.demo.real_splat import DEFAULT_SCENE, build_photoreal_sample, copy_splat_to_job
from backend.pipeline.export.glb import glb_is_valid, write_glb
from backend.pipeline.export.mesh import export_mesh
from backend.pipeline.export.ply import write_ascii_ply
from backend.pipeline.export.pointcloud import export_pointcloud
from backend.pipeline.export.preview import write_preview
from backend.pipeline.export.report import write_report
from backend.pipeline.ingest.quality import select_keyframes, write_frame_quality
from backend.pipeline.ingest.video import collect_source_frames, save_frames
from backend.pipeline.jobs.job_manager import job_manager
from backend.pipeline.reconstruct.checks import assess_frames
from backend.pipeline.reconstruct.colmap.detector import check_colmap_installation
from backend.pipeline.reconstruct.colmap.parser import read_ply
from backend.pipeline.reconstruct.colmap.runner import ColmapCancelled
from backend.pipeline.reconstruct.colmap.service import ColmapMissing, ColmapService
from backend.pipeline.reconstruct.colmap.workspace import ColmapWorkspace
from backend.pipeline.reconstruct.deps import check_openmvs_installation
from backend.pipeline.reconstruct.openmvs.service import OpenMVSMissing, OpenMVSService
from backend.pipeline.reconstruct.quality_score import reconstruction_quality_score


def _raise_if_cancelled(job_id: str) -> None:
    if job_manager.is_cancelled(job_id):
        raise ColmapCancelled("Reconstruction was cancelled.")


def _progress(job_id: str, stage: str, percent: int, message: str) -> None:
    _raise_if_cancelled(job_id)
    update_job(
        job_id,
        status="running",
        progress={"stage": stage, "percent": percent, "message": message},
        log=message,
    )


def run_job(job_id: str) -> None:
    _raise_if_cancelled(job_id)
    record = load_job(job_id)
    fields = {"status": "running"}
    if not record.get("started_at"):
        fields["started_at"] = utc_now()
    record = update_job(job_id, **fields)
    if record.get("is_demo"):
        _run_demo(job_id)
        return
    try:
        _run_reconstruction(job_id)
    finally:
        job_manager.finish(job_id)


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


class _Pipeline:
    def __init__(self, colmap: ColmapService | None = None, openmvs: OpenMVSService | None = None):
        self.colmap = colmap
        self.openmvs = openmvs

    def cancel(self) -> None:
        if self.colmap:
            self.colmap.cancel()
        if self.openmvs:
            self.openmvs.cancel()


def _run_reconstruction(job_id: str) -> None:
    root = job_dir(job_id)
    ws = ColmapWorkspace(root)
    ws.create()
    cancel = job_manager.event_for(job_id)
    handles = _Pipeline()
    job_manager.register(job_id, handles)
    if cancel.is_set():
        raise ColmapCancelled("Reconstruction was cancelled.")

    apply_job_quality(load_job(job_id).get("quality"))
    _progress(job_id, "ingesting", 8, "Reading video / photos")

    existing_images = sorted(ws.images.glob("frame_*.jpg"))
    if ws.stage_done("frameSelection") and len(existing_images) >= MIN_FRAMES:
        frames = existing_images
        image_paths = existing_images
        thumbs = list((ws.output / "thumbs").glob("thumb_*.jpg"))
        _progress(job_id, "selecting", 24, f"Resuming with {len(frames)} selected frames")
    else:
        def _ingest_progress(kept: int, target: int, name: str) -> None:
            _raise_if_cancelled(job_id)
            pct = 8 + int(10 * kept / max(target, 1))
            _progress(job_id, "extracting", pct, f"Extracting frames from {name} — {kept} of {target}")

        raw_frames = collect_source_frames(ws.input, on_progress=_ingest_progress)
        ws.set_stage("frameExtraction", "completed", extractedCandidates=len(raw_frames))
        _progress(job_id, "extracting", 16, f"Extracted {len(raw_frames)} candidate frames")

        frames, kept_idx = select_keyframes(raw_frames)
        assess_frames(frames)
        if len(frames) < MIN_FRAMES:
            raise RuntimeError(f"Too few usable frames after quality filtering ({len(frames)}).")
        save_frames(frames, ws.frames)
        image_paths = _write_colmap_images(frames, ws.images)
        write_frame_quality(ws.output / "frame_quality.json", raw_frames, kept_idx)
        thumbs = _save_thumbs(frames, ws.output / "thumbs")
        ws.set_stage("frameSelection", "completed", inputFrames=len(frames), selectedIndices=kept_idx)
        update_job(job_id, frame_count=len(frames))
        _progress(job_id, "selecting", 24, f"Selected {len(frames)} overlapping frames")

    colmap_info = check_colmap_installation()
    if not colmap_info.get("installed"):
        raise ColmapMissing()

    device_note = (
        "Running COLMAP in CPU mode"
        if colmap_info.get("device") == "cpu"
        else "Running COLMAP with GPU acceleration"
    )
    _progress(job_id, "features", 30, device_note)

    service = ColmapService(
        ws,
        info=colmap_info,
        cancel_event=cancel,
        on_progress=lambda stage, pct, msg: _progress(job_id, stage, pct, msg),
    )
    handles.colmap = service

    if not ws.stage_done("featureExtraction") or not ws.database.exists():
        service.extract_features()
    if not ws.stage_done("matching"):
        service.match_features()
    if not ws.stage_done("sfm"):
        service.run_mapper()

    sparse = _sparse_with_recovery(service, len(image_paths))
    model_dir = Path(sparse["modelDir"])
    if not ws.stage_done("undistortion"):
        service.undistort_images(model_dir)
    _export_sparse_ply(model_dir, ws.output / "sparse.ply")

    fused, dense_backend = _run_dense_local(job_id, ws, service, handles, cancel)
    cleaned, dense = service.validate_and_clean_cloud(fused) if dense_backend == "colmap" else handles.openmvs.validate_cloud(fused)
    shutil.copy2(cleaned, ws.output / "pointcloud.ply")

    xyz, rgb, faces, mesh_info, _unused_texture, _artifact = _run_mesh_local(
        job_id, ws, service, handles, cleaned, fused, dense_backend
    )

    _progress(job_id, "glb", 94, "Creating and validating GLB")
    glb_path = ws.output / "model.glb"
    # Always vertex colour from the mesh. OpenMVS photo atlases show up as
    # rainbow static in the viewer, so they are never the default model.
    write_glb(glb_path, xyz, faces, rgb)
    glb_ok, glb_why = glb_is_valid(glb_path)
    artifact = "VERTEX-COLORED 3D MESH"
    use_photo = False
    if not glb_ok:
        raise RuntimeError(f"GLB conversion failed: {glb_why}")
    ws.set_stage("glb", "completed")

    cloud_xyz, cloud_rgb, _ = read_ply(cleaned)
    export_pointcloud(ws.output, cloud_xyz, cloud_rgb, np.ones(len(cloud_xyz), dtype=np.float32))
    export_mesh(ws.output, xyz, rgb, np.ones(len(xyz), dtype=np.float32), faces=faces)
    write_preview(ws.output, cloud_xyz, cloud_rgb, frames)

    qscore = reconstruction_quality_score(sparse, dense, mesh_info)
    if qscore["status"] == "FAILED" or not dense.get("ok") or not mesh_info.get("ok"):
        raise RuntimeError(
            "Reconstruction failed quality validation. "
            + (qscore["notes"][0] if qscore["notes"] else f"Quality score {qscore['label']}.")
        )

    pipeline = (
        "COLMAP SfM + OpenMVS dense/mesh/texture"
        if dense_backend == "openmvs"
        else "COLMAP SfM + PatchMatch MVS + Poisson"
    )
    quality = {
        "input_frames": len(frames),
        "usable_frames": len(frames),
        "registered_frames": sparse["registeredFrames"],
        "registration_ratio": sparse["registrationRatio"],
        "sparse_points": sparse["sparsePoints"],
        "dense_points": dense["densePoints"],
        "mesh_vertices": mesh_info["meshVertices"],
        "mesh_triangles": mesh_info["meshTriangles"],
        "connected_components": mesh_info["components"],
        "mean_reprojection_error": sparse["meanReprojectionError"],
        "status": qscore["status"].lower(),
        "quality_score": qscore["score"],
        "device": "cpu" if colmap_info.get("device") == "cpu" else "gpu",
        "pipeline": pipeline,
        "artifact": artifact,
        "textured": bool(use_photo),
        "denseBackend": dense_backend,
    }
    ws.write_quality(quality)
    if not RECONSTRUCTION_DEBUG:
        ws.cleanup_intermediates()

    files = {
        "glb": "model.glb",
        "mesh": "mesh.ply",
        "obj": "mesh.obj",
        "pointcloud": "pointcloud.ply",
        "sparse": "sparse.ply",
        "preview": "preview.jpg",
        "report": "report.json",
        "quality": "quality.json",
        "frame_quality": "frame_quality.json",
    }
    report = {
        "job_id": job_id,
        "demo": False,
        "pipeline": pipeline,
        "artifact": artifact,
        "point_count": int(dense["densePoints"]),
        "triangle_count": int(mesh_info["meshTriangles"]),
        "frame_count": len(frames),
        "metric": False,
        "units": "relative units",
        "has_gps": False,
        "thumbs": [p.name for p in thumbs],
        "metrics": {
            "inputFrames": len(frames),
            "registeredFrames": sparse["registeredFrames"],
            "registrationRatio": sparse["registrationRatio"],
            "sparsePoints": sparse["sparsePoints"],
            "densePoints": dense["densePoints"],
            "meshVertices": mesh_info["meshVertices"],
            "meshTriangles": mesh_info["meshTriangles"],
            "reprojectionError": sparse["meanReprojectionError"],
            "components": mesh_info["components"],
            "device": colmap_info.get("device"),
            "pipeline": pipeline,
            "textured": bool(use_photo),
            "qualityScore": qscore["score"],
            "qualityStatus": qscore["status"],
            "denseBackend": dense_backend,
        },
        "confidence": {
            "mean": qscore["score"] / 100.0,
            "note": f"{artifact} via {pipeline}. Quality {qscore['label']} ({qscore['status']}).",
            "preview": False,
            "mesh": True,
            "textured": bool(use_photo),
        },
        "files": files,
        "quality": quality,
        "sparse": {k: v for k, v in sparse.items() if k != "trajectory"},
        "dense": dense,
        "mesh": mesh_info,
    }
    write_report(ws.output, report)
    update_job(
        job_id,
        status="done",
        metric=False,
        point_count=int(dense["densePoints"]),
        triangle_count=int(mesh_info["meshTriangles"]),
        frame_count=len(frames),
        result=report,
        progress={"stage": "done", "percent": 100, "message": "Local reconstruction complete"},
        log="Local COLMAP/OpenMVS exports written",
    )


def _sparse_with_recovery(service: ColmapService, n_images: int) -> dict:
    last_error = None
    for attempt in range(3):
        try:
            return service.validate_sparse_model(n_images)
        except RuntimeError as exc:
            last_error = exc
            if attempt >= 2:
                break
            service.rematch_wider()
            service.reset_sparse()
            service.run_mapper()
    raise RuntimeError(str(last_error) if last_error else "Insufficient camera registration.")


def _run_dense_local(job_id, ws, service, handles, cancel) -> tuple[Path, str]:
    existing = ws.openmvs / "scene_dense.ply"
    openmvs_info = check_openmvs_installation()
    if existing.exists() and existing.stat().st_size > 1000 and openmvs_info.get("installed"):
        _progress(job_id, "dense", 74, "Resuming from the existing OpenMVS dense point cloud")
        ovs = OpenMVSService(
            ws.root,
            ws.logs,
            cancel_event=cancel,
            on_progress=lambda stage, pct, msg: _progress(job_id, stage, pct, msg),
            info=openmvs_info,
        )
        handles.openmvs = ovs
        return existing, "openmvs"

    want = DENSE_BACKEND
    colmap_info = service.info

    if want in {"auto", "colmap"} and colmap_info.get("cuda"):
        _progress(job_id, "dense", 66, "COLMAP PatchMatch is available — using it")
        fused = service.try_colmap_dense()
        if fused is not None:
            return fused, "colmap"
        if want == "colmap":
            raise RuntimeError("COLMAP dense reconstruction is not available on this machine.")

    if want in {"auto", "colmap"} and not colmap_info.get("cuda"):
        _progress(job_id, "dense", 64, "Checking whether COLMAP dense stereo can run on CPU")
        fused = service.try_colmap_dense()
        if fused is not None:
            return fused, "colmap"

    if not openmvs_info.get("installed"):
        raise OpenMVSMissing()

    _progress(job_id, "dense", 65, "Using OpenMVS for local dense reconstruction")
    ovs = OpenMVSService(
        ws.root,
        ws.logs,
        cancel_event=cancel,
        on_progress=lambda stage, pct, msg: _progress(job_id, stage, pct, msg),
        info=openmvs_info,
    )
    handles.openmvs = ovs
    scene = ovs.import_colmap(ws.dense)
    ply = ovs.densify(scene)
    return ply, "openmvs"


def _run_mesh_local(job_id, ws, service, handles, cleaned, fused, dense_backend):
    refined = ws.openmvs / "scene_dense_mesh_refine.ply"
    if (
        dense_backend == "openmvs"
        and handles.openmvs
        and refined.exists()
        and refined.stat().st_size > 1000
    ):
        _progress(job_id, "meshing", 86, "Resuming from the existing OpenMVS mesh")
        xyz, rgb, faces, mesh_info = handles.openmvs.validate_mesh_file(refined, cleaned)
        return xyz, rgb, faces, mesh_info, None, "VERTEX-COLORED 3D MESH"

    if dense_backend == "openmvs" and handles.openmvs:
        mesh_ply = handles.openmvs.reconstruct_mesh(ws.root / "openmvs" / "scene_dense.mvs")
        mesh_ply = handles.openmvs.refine_mesh(mesh_ply)
        shutil.copy2(mesh_ply, ws.mesh / mesh_ply.name)
        xyz, rgb, faces, mesh_info = handles.openmvs.validate_mesh_file(mesh_ply, cleaned)
        return xyz, rgb, faces, mesh_info, None, "VERTEX-COLORED 3D MESH"

    mesh_path = service.create_mesh(cleaned)
    mesh_path = service.simplify_mesh(mesh_path)
    xyz, rgb, faces, mesh_info = service.load_validated_mesh(mesh_path, cleaned)
    return xyz, rgb, faces, mesh_info, None, "VERTEX-COLORED 3D MESH"


def _export_sparse_ply(model_dir: Path, dest: Path) -> None:
    points = model_dir / "points3D.txt"
    if not points.exists():
        return
    xyz = []
    rgb = []
    for line in points.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        xyz.append((float(parts[1]), float(parts[2]), float(parts[3])))
        rgb.append((int(parts[4]), int(parts[5]), int(parts[6])))
    if xyz:
        write_ascii_ply(dest, np.asarray(xyz), rgb=np.asarray(rgb, dtype=np.uint8))


def _write_colmap_images(frames: list[np.ndarray], folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.jpg"):
        old.unlink()
    paths = []
    for i, frame in enumerate(frames, start=1):
        path = folder / f"frame_{i:06d}.jpg"
        cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 93])
        paths.append(path)
    return paths


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
