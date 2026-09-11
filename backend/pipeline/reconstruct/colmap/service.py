from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from backend.app.config import MESH_METHOD, quality_preset
from backend.pipeline.reconstruct.colmap.detector import check_colmap_installation
from backend.pipeline.reconstruct.colmap.parser import (
    color_mesh_from_cloud,
    list_sparse_models,
    parse_sparse_model,
    read_ply,
    statistical_filter,
)
from backend.pipeline.reconstruct.colmap.runner import ColmapCancelled, ColmapRunner
from backend.pipeline.reconstruct.colmap.validator import validate_dense, validate_mesh, validate_sparse
from backend.pipeline.reconstruct.colmap.workspace import ColmapWorkspace


ProgressCb = Callable[[str, int, str], None]


class ColmapMissing(RuntimeError):
    def __init__(self):
        super().__init__("COLMAP is not installed on this machine.")


class ColmapService:
    def __init__(
        self,
        workspace: ColmapWorkspace,
        info: dict | None = None,
        cancel_event: threading.Event | None = None,
        on_progress: ProgressCb | None = None,
    ):
        self.ws = workspace
        self.info = info or check_colmap_installation()
        if not self.info.get("installed"):
            raise ColmapMissing()
        self.use_gpu = self.info.get("device") == "gpu"
        self.runner = ColmapRunner(self.info["path"], workspace.logs, cancel_event=cancel_event)
        self.on_progress = on_progress
        preset = quality_preset()
        self.max_image_size = int(preset["max_image_size"])
        self.match_overlap = int(preset["match_overlap"])
        self.face_ratio = float(preset["face_ratio"])
        self.mesh_method = MESH_METHOD if MESH_METHOD in {"poisson", "delaunay"} else "poisson"

    def cancel(self) -> None:
        self.runner.cancel()

    def _progress(self, stage: str, percent: int, message: str) -> None:
        if self.on_progress:
            self.on_progress(stage, percent, message)

    def _gpu_flag(self, group: str) -> list[str]:
        value = "1" if self.use_gpu else "0"
        return [f"--{group}.use_gpu", value]

    def _run_with_gpu_groups(self, args: list[str], log_name: str, groups: tuple[str, ...]) -> dict:
        last_error: Exception | None = None
        for group in groups:
            try:
                return self.runner.run([*args, *self._gpu_flag(group)], log_name)
            except RuntimeError as exc:
                last_error = exc
                if "unrecognized" in str(exc).lower() or "unknown option" in str(exc).lower():
                    continue
                raise
        if last_error:
            raise last_error
        return self.runner.run(args, log_name)

    def extract_features(self) -> dict:
        self._progress("features", 34, "Extracting COLMAP features")
        args = [
            "feature_extractor",
            "--database_path",
            str(self.ws.database),
            "--image_path",
            str(self.ws.images),
            "--ImageReader.single_camera",
            "1",
            "--ImageReader.camera_model",
            "SIMPLE_RADIAL",
            "--FeatureExtraction.max_image_size",
            str(self.max_image_size),
        ]
        result = self._run_with_gpu_groups(args, "feature_extractor.log", ("FeatureExtraction", "SiftExtraction"))
        self.ws.set_stage("featureExtraction", "completed")
        return result

    def match_features(self) -> dict:
        self._progress("matching", 42, "Matching sequential video frames")
        args = [
            "sequential_matcher",
            "--database_path",
            str(self.ws.database),
            "--SequentialMatching.overlap",
            str(self.match_overlap),
            "--SequentialMatching.quadratic_overlap",
            "1",
            "--SequentialMatching.loop_detection",
            "0",
        ]
        if not self.use_gpu:
            args += ["--SiftMatching.cpu_brute_force_matcher", "1"]
        try:
            result = self._run_with_gpu_groups(args, "matcher.log", ("FeatureMatching", "SiftMatching"))
        except RuntimeError as exc:
            if "loop" in str(exc).lower() or "vocab" in str(exc).lower():
                args = [
                    "sequential_matcher",
                    "--database_path",
                    str(self.ws.database),
                    "--SequentialMatching.overlap",
                    str(self.match_overlap),
                    "--SequentialMatching.quadratic_overlap",
                    "1",
                    "--SequentialMatching.loop_detection",
                    "0",
                ]
                if not self.use_gpu:
                    args += ["--SiftMatching.cpu_brute_force_matcher", "1"]
                result = self._run_with_gpu_groups(args, "matcher.log", ("FeatureMatching", "SiftMatching"))
            else:
                raise
        self.ws.set_stage("matching", "completed")
        return result

    def rematch_wider(self) -> dict:
        self.match_overlap = min(int(self.match_overlap) + 8, 32)
        self._progress("matching", 44, f"Retrying matching with overlap {self.match_overlap}")
        return self.match_features()

    def reset_sparse(self) -> None:
        import shutil

        if self.ws.sparse.exists():
            shutil.rmtree(self.ws.sparse)
        self.ws.sparse.mkdir(parents=True, exist_ok=True)
        self.ws.set_stage("sfm", "pending")
        self.ws.set_stage("sparseValidation", "pending")

    def try_colmap_dense(self) -> Path | None:
        """Return fused.ply if COLMAP PatchMatch works. None if this build needs CUDA."""
        try:
            self.run_patch_match()
            return self.fuse_stereo()
        except RuntimeError as exc:
            text = str(exc).lower()
            if "cuda" in text or "cpu mode" in text or "dense stereo" in text:
                return None
            raise

    def run_mapper(self) -> Path:
        self._progress("cameras", 50, "Reconstructing camera poses (COLMAP mapper)")
        self.ws.sparse.mkdir(parents=True, exist_ok=True)
        self.runner.run(
            [
                "mapper",
                "--database_path",
                str(self.ws.database),
                "--image_path",
                str(self.ws.images),
                "--output_path",
                str(self.ws.sparse),
            ],
            "mapper.log",
        )
        models = list_sparse_models(self.ws.sparse)
        if not models:
            raise RuntimeError("COLMAP mapper finished without a sparse model.")
        self.ws.set_stage("sfm", "completed", components=len(models))
        return models[0]

    def export_model_txt(self, model_dir: Path) -> Path:
        if (model_dir / "images.txt").exists() and (model_dir / "points3D.txt").exists():
            return model_dir
        self.runner.run(
            [
                "model_converter",
                "--input_path",
                str(model_dir),
                "--output_path",
                str(model_dir),
                "--output_type",
                "TXT",
            ],
            "model_converter.log",
        )
        return model_dir

    def validate_sparse_model(self, total_images: int) -> dict:
        self._progress("validating_sparse", 56, "Validating sparse reconstruction")
        models = list_sparse_models(self.ws.sparse)
        if not models:
            raise RuntimeError("No COLMAP sparse model was written.")
        parsed = []
        for model in models:
            self.export_model_txt(model)
            parsed.append(parse_sparse_model(model))
        parsed.sort(key=lambda item: item["registered_images"], reverse=True)
        best = parsed[0]
        report = validate_sparse(
            total_images=total_images,
            registered=best["registered_images"],
            sparse_points=best["sparse_points"],
            components=len(models),
            mean_reproj=best["mean_reprojection_error"],
            centers=best["centers"],
        )
        report["modelDir"] = best["model_dir"]
        self.ws.set_stage(
            "sparseValidation",
            "completed" if report["ok"] else "failed",
            **{
                "inputFrames": total_images,
                "registeredFrames": best["registered_images"],
                "sparsePoints": best["sparse_points"],
                "meanReprojectionError": best["mean_reprojection_error"],
                "components": len(models),
            },
        )
        if not report["ok"]:
            raise RuntimeError(report["message"])
        return report

    def undistort_images(self, model_dir: Path) -> dict:
        self._progress("undistorting", 60, "Undistorting images")
        result = self.runner.run(
            [
                "image_undistorter",
                "--image_path",
                str(self.ws.images),
                "--input_path",
                str(model_dir),
                "--output_path",
                str(self.ws.dense),
                "--output_type",
                "COLMAP",
                "--max_image_size",
                str(self.max_image_size),
            ],
            "undistorter.log",
        )
        self.ws.set_stage("undistortion", "completed")
        return result

    def run_patch_match(self) -> dict:
        self._progress("dense", 66, "Running PatchMatch MVS")
        if not self.use_gpu:
            self._progress("dense", 66, "Running COLMAP in CPU mode — attempting dense stereo")
        args = [
            "patch_match_stereo",
            "--workspace_path",
            str(self.ws.dense),
            "--workspace_format",
            "COLMAP",
            "--PatchMatchStereo.geom_consistency",
            "true",
        ]
        result = self.runner.run(args, "patchmatch.log")
        self.ws.set_stage("mvs", "completed")
        return result

    def fuse_stereo(self) -> Path:
        self._progress("fusion", 74, "Fusing the dense point cloud")
        fused = self.ws.dense / "fused.ply"
        self.runner.run(
            [
                "stereo_fusion",
                "--workspace_path",
                str(self.ws.dense),
                "--workspace_format",
                "COLMAP",
                "--input_type",
                "geometric",
                "--output_path",
                str(fused),
            ],
            "fusion.log",
        )
        if not fused.exists() or fused.stat().st_size < 80:
            raise RuntimeError("Stereo fusion did not write a dense point cloud.")
        self.ws.set_stage("fusion", "completed")
        return fused

    def validate_and_clean_cloud(self, fused: Path) -> tuple[Path, dict]:
        xyz, rgb, _faces = read_ply(fused)
        cleaned_xyz, cleaned_rgb = statistical_filter(xyz, rgb)
        report = validate_dense(cleaned_xyz)
        self.ws.set_stage(
            "denseValidation",
            "completed" if report["ok"] else "failed",
            densePoints=int(len(cleaned_xyz)),
        )
        if not report["ok"]:
            raise RuntimeError(report["message"])
        cleaned = self.ws.dense / "fused_clean.ply"
        from backend.pipeline.export.ply import write_ascii_ply

        write_ascii_ply(cleaned, cleaned_xyz, rgb=cleaned_rgb)
        return cleaned, {**report, "densePoints": int(len(cleaned_xyz))}

    def create_mesh(self, cloud_path: Path) -> Path:
        self._progress("meshing", 80, f"Generating {self.mesh_method} mesh")
        meshed = self.ws.dense / f"meshed-{self.mesh_method}.ply"
        command = "poisson_mesher" if self.mesh_method == "poisson" else "delaunay_mesher"
        try:
            self.runner.run(
                ["poisson_mesher" if command == "poisson_mesher" else "delaunay_mesher",
                 "--input_path", str(cloud_path),
                 "--output_path", str(meshed)],
                "mesher.log",
            )
        except RuntimeError:
            if command == "poisson_mesher":
                meshed = self.ws.dense / "meshed-delaunay.ply"
                self.runner.run(
                    ["delaunay_mesher", "--input_path", str(cloud_path), "--output_path", str(meshed)],
                    "mesher.log",
                )
            else:
                raise
        if not meshed.exists():
            raise RuntimeError("COLMAP mesher did not write a mesh.")
        self.ws.set_stage("meshing", "completed")
        return meshed

    def simplify_mesh(self, mesh_path: Path) -> Path:
        if not self.info.get("has_mesh_simplifier"):
            self.ws.set_stage("simplification", "skipped")
            return mesh_path
        self._progress("simplifying", 86, "Simplifying the mesh")
        out = self.ws.output / "mesh-simplified.ply"
        try:
            self.runner.run(
                [
                    "mesh_simplifier",
                    "--input_path",
                    str(mesh_path),
                    "--output_path",
                    str(out),
                    "--MeshSimplification.target_face_ratio",
                    str(self.face_ratio),
                ],
                "simplifier.log",
            )
        except RuntimeError:
            self.ws.set_stage("simplification", "skipped")
            return mesh_path
        self.ws.set_stage("simplification", "completed")
        return out if out.exists() else mesh_path

    def texture_mesh(self, mesh_path: Path) -> Path | None:
        if not self.info.get("has_mesh_texturer"):
            self.ws.set_stage("texturing", "skipped")
            return None
        self._progress("texturing", 90, "Texturing the mesh from undistorted images")
        out_dir = self.ws.output / "textured"
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.runner.run(
                [
                    "mesh_texturer",
                    "--workspace_path",
                    str(self.ws.dense),
                    "--input_path",
                    str(mesh_path),
                    "--output_path",
                    str(out_dir),
                ],
                "texturer.log",
            )
        except RuntimeError:
            self.ws.set_stage("texturing", "failed")
            return None
        self.ws.set_stage("texturing", "completed")
        for name in ("textured.obj", "mesh.obj", "textured.ply"):
            candidate = out_dir / name
            if candidate.exists():
                return candidate
        found = next(out_dir.glob("*.obj"), None)
        return found

    def load_validated_mesh(self, mesh_path: Path, cloud_path: Path) -> tuple[object, object, object, dict]:
        xyz, rgb, faces = read_ply(mesh_path)
        cloud_xyz, cloud_rgb, _ = read_ply(cloud_path)
        if rgb is None or len(rgb) != len(xyz) or (rgb == 180).all():
            rgb = color_mesh_from_cloud(xyz, cloud_xyz, cloud_rgb)
        report = validate_mesh(xyz, faces)
        if not report["ok"]:
            raise RuntimeError(report["message"])
        return xyz, rgb, faces, report
