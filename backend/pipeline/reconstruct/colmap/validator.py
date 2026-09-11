from __future__ import annotations

from backend.app.config import (
    MAX_REPROJ_ERROR,
    MIN_DENSE_POINTS,
    MIN_REGISTRATION_RATIO,
    MIN_SPARSE_POINTS,
    PREFERRED_REGISTRATION_RATIO,
)
from backend.pipeline.reconstruct.colmap.parser import cloud_extent, mesh_components, trajectory_stats
from backend.pipeline.reconstruct.diagnostics import cloud_components


def classify_status(warnings: list[str], failed: list[str]) -> str:
    if failed:
        return "FAILED"
    if warnings:
        return "WARNING"
    return "GOOD"


def validate_sparse(
    total_images: int,
    registered: int,
    sparse_points: int,
    components: int,
    mean_reproj: float,
    centers,
    min_ratio: float = MIN_REGISTRATION_RATIO,
    preferred_ratio: float = PREFERRED_REGISTRATION_RATIO,
    max_reproj: float = MAX_REPROJ_ERROR,
    min_points: int = MIN_SPARSE_POINTS,
) -> dict:
    ratio = registered / max(total_images, 1)
    traj = trajectory_stats(centers)
    failed: list[str] = []
    warnings: list[str] = []

    if registered < 8:
        failed.append(
            f"Only {registered} of {total_images} frames were registered. "
            "The camera trajectory could not be reconstructed reliably."
        )
    elif ratio < min_ratio:
        failed.append(
            f"Only {registered} of {total_images} frames were registered "
            f"({ratio:.0%}). Insufficient camera registration."
        )
    elif ratio < preferred_ratio:
        warnings.append(
            f"Only {registered} of {total_images} frames were registered ({ratio:.0%}). "
            "Reconstruction quality may be poor because the video contains insufficient visual overlap."
        )

    if components > 1:
        failed.append(
            f"COLMAP produced {components} disconnected reconstruction components. "
            "They were not merged. Improve matching overlap and retry."
        )

    if sparse_points < min_points:
        failed.append(
            f"Sparse reconstruction has only {sparse_points} points. "
            "That is not enough structure for a reliable scene."
        )

    if mean_reproj > max_reproj:
        failed.append(
            f"Mean reprojection error is {mean_reproj:.2f} px (limit {max_reproj:.1f} px)."
        )

    if traj["large_jumps"] > max(2, registered // 20):
        warnings.append(
            "Registered camera poses contain sudden jumps. "
            "The trajectory may not be a continuous walkthrough."
        )

    status = classify_status(warnings, failed)
    return {
        "inputFrames": total_images,
        "registeredFrames": registered,
        "registrationRatio": ratio,
        "sparsePoints": sparse_points,
        "components": components,
        "meanReprojectionError": mean_reproj,
        "trajectory": traj,
        "warnings": warnings,
        "failed": failed,
        "status": status,
        "ok": status != "FAILED",
        "message": failed[0] if failed else (warnings[0] if warnings else "Sparse reconstruction looks usable."),
    }


def validate_dense(xyz, min_points: int = MIN_DENSE_POINTS) -> dict:
    extent = cloud_extent(xyz)
    comps = cloud_components(xyz) if len(xyz) else {"components": 0, "largest_frac": 0.0, "sizes": []}
    failed: list[str] = []
    warnings: list[str] = []
    if extent["count"] < min_points:
        failed.append(
            f"Dense point cloud has only {extent['count']} points. "
            "That is too sparse to mesh a complete scene."
        )
    if extent["diagonal"] <= 1e-6:
        failed.append("Dense point cloud bounding box is empty.")
    largest = float(comps.get("largest_frac") or 0.0)
    # Dense MVS clouds are uneven; kNN graphs over-split them. Fail only when
    # the cloud is clearly a spray of tiny clusters, not a room-scale surface.
    if extent["count"] >= 200 and extent["diagonal"] > 1e-3 and largest < 0.18:
        failed.append(
            "The dense point cloud is mostly tiny isolated clusters. "
            "It will not be meshed."
        )
    elif extent["count"] >= 200 and largest < 0.55:
        warnings.append("The dense point cloud has noticeable disconnected fragments.")
    status = classify_status(warnings, failed)
    return {
        "densePoints": extent["count"],
        "bbox": extent["bbox"],
        "diagonal": extent["diagonal"],
        "components": int(comps.get("components") or 0),
        "largestFraction": largest,
        "warnings": warnings,
        "failed": failed,
        "status": status,
        "ok": status != "FAILED",
        "message": failed[0] if failed else (warnings[0] if warnings else "Dense point cloud is spatially coherent."),
    }


def validate_mesh(xyz, faces) -> dict:
    n_verts = len(xyz)
    n_faces = len(faces)
    failed: list[str] = []
    warnings: list[str] = []
    if n_verts < 50 or n_faces < 40:
        failed.append(f"Mesh is too small ({n_verts} vertices, {n_faces} triangles).")
    comps = mesh_components(faces, n_verts)
    largest = float(comps.get("largest_frac") or 0.0)
    if n_faces >= 80 and largest < 0.50:
        failed.append(
            "The mesh is mostly tiny disconnected islands. "
            "A high triangle count does not mean a successful reconstruction."
        )
    elif n_faces >= 80 and largest < 0.85:
        warnings.append("The mesh has more than one large connected piece.")
    extent = cloud_extent(xyz)
    if extent["diagonal"] <= 1e-6:
        failed.append("Mesh bounding box is empty.")
    status = classify_status(warnings, failed)
    return {
        "meshVertices": n_verts,
        "meshTriangles": n_faces,
        "components": int(comps.get("components") or 0),
        "largestFraction": largest,
        "bbox": extent["bbox"],
        "warnings": warnings,
        "failed": failed,
        "status": status,
        "ok": status != "FAILED",
        "message": failed[0] if failed else (warnings[0] if warnings else "Mesh occupies a coherent volume."),
    }
