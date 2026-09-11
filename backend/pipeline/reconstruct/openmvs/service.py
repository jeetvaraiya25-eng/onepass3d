from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

from backend.app.config import MAX_DENSE_IMAGE_SIZE, quality_preset
from backend.pipeline.reconstruct.colmap.parser import read_ply, statistical_filter
from backend.pipeline.reconstruct.colmap.runner import ColmapRunner
from backend.pipeline.reconstruct.colmap.validator import validate_dense, validate_mesh
from backend.pipeline.reconstruct.deps import check_openmvs_installation


ProgressCb = Callable[[str, int, str], None]


class OpenMVSMissing(RuntimeError):
    def __init__(self, message: str | None = None):
        super().__init__(
            message
            or (
                "OpenMVS is not installed on this machine. "
                "Place the official macOS arm64 binaries in tools/openmvs "
                "or set OPENMVS_PATH."
            )
        )


class OpenMVSService:
    def __init__(
        self,
        job_root: Path,
        logs_dir: Path,
        cancel_event: threading.Event | None = None,
        on_progress: ProgressCb | None = None,
        info: dict | None = None,
    ):
        self.info = info or check_openmvs_installation()
        if not self.info.get("installed"):
            raise OpenMVSMissing(self.info.get("message"))
        self.root = Path(job_root)
        self.work = self.root / "openmvs"
        self.work.mkdir(parents=True, exist_ok=True)
        self.bins = self.info["binaries"]
        self.runner = ColmapRunner(self.bins["DensifyPointCloud"], logs_dir, cancel_event=cancel_event)
        self.on_progress = on_progress
        preset = quality_preset()
        self.max_resolution = min(int(preset["max_image_size"]), MAX_DENSE_IMAGE_SIZE)
        self.resolution_level = 1 if quality_preset()["max_frames"] <= 180 else 0
        self.number_views = 6
        self.number_views_fuse = 3
        self.refine_decimate = 0.8
        self.texture_resolution_level = 0
        cores = os.cpu_count() or 4
        self.max_threads = max(2, min(cores - 2, 6))

    def cancel(self) -> None:
        self.runner.cancel()

    def _progress(self, stage: str, percent: int, message: str) -> None:
        if self.on_progress:
            self.on_progress(stage, percent, message)

    def _run(self, name: str, args: list[str], log_name: str) -> dict:
        binary = self.bins.get(name)
        if not binary:
            raise OpenMVSMissing(f"OpenMVS binary missing: {name}")
        return self.runner.run(args, log_name, binary=binary)

    def import_colmap(self, colmap_dense: Path) -> Path:
        self._progress("preparing_dense", 62, "Importing COLMAP cameras into OpenMVS")
        scene = self.work / "scene.mvs"
        self._run(
            "InterfaceCOLMAP",
            [
                "--working-folder",
                str(colmap_dense),
                "--input-file",
                str(colmap_dense),
                "--output-file",
                str(scene),
                "--image-folder",
                "images/",
            ],
            "openmvs_import.log",
        )
        if not scene.exists():
            raise RuntimeError("OpenMVS could not import the COLMAP reconstruction.")
        return scene

    def densify(self, scene: Path) -> Path:
        self._progress("dense", 68, "OpenMVS dense reconstruction (local CPU)")
        out = self.work / "scene_dense.mvs"
        self._run(
            "DensifyPointCloud",
            [
                "--working-folder",
                str(self.work),
                "--input-file",
                str(scene),
                "--output-file",
                str(out),
                "--resolution-level",
                str(self.resolution_level),
                "--max-resolution",
                str(self.max_resolution),
                "--min-resolution",
                "480",
                "--number-views",
                str(self.number_views),
                "--number-views-fuse",
                str(self.number_views_fuse),
                "--max-threads",
                str(self.max_threads),
                "--remove-dmaps",
                "1",
            ],
            "openmvs.log",
        )
        ply = self.work / "scene_dense.ply"
        if not ply.exists():
            found = next(self.work.glob("*dense*.ply"), None)
            if found:
                ply = found
        if not ply.exists():
            raise RuntimeError("OpenMVS densify did not write a dense point cloud.")
        return ply

    def reconstruct_mesh(self, scene_dense: Path) -> Path:
        self._progress("meshing", 80, "OpenMVS mesh reconstruction")
        mesh_mvs = self.work / "scene_dense_mesh.mvs"
        self._run(
            "ReconstructMesh",
            [
                "--working-folder",
                str(self.work),
                "--input-file",
                str(scene_dense if scene_dense.suffix == ".mvs" else self.work / "scene_dense.mvs"),
                "--output-file",
                str(mesh_mvs),
                "--max-threads",
                str(self.max_threads),
            ],
            "meshing.log",
        )
        ply = self.work / "scene_dense_mesh.ply"
        if not ply.exists():
            found = next(self.work.glob("*mesh*.ply"), None)
            if found:
                ply = found
        if not ply.exists():
            raise RuntimeError("OpenMVS ReconstructMesh did not write a mesh.")
        return ply

    def refine_mesh(self, mesh_ply: Path) -> Path:
        if not quality_preset().get("prefer_photo_texture"):
            self._progress("refining", 86, "Keeping the full mesh for Normal quality")
            return mesh_ply
        self._progress("refining", 86, "Refining the OpenMVS mesh")
        refined = self.work / "scene_dense_mesh_refine.mvs"
        try:
            self._run(
                "RefineMesh",
                [
                    "--working-folder",
                    str(self.work),
                    "--input-file",
                    str(self.work / "scene_dense.mvs"),
                    "--mesh-file",
                    str(mesh_ply),
                    "--output-file",
                    str(refined),
                    "--decimate",
                    str(self.refine_decimate),
                    "--max-threads",
                    str(self.max_threads),
                    "--resolution-level",
                    "1",
                ],
                "refine.log",
            )
        except RuntimeError:
            return mesh_ply
        ply = self.work / "scene_dense_mesh_refine.ply"
        return ply if ply.exists() else mesh_ply

    def texture_mesh(self, mesh_ply: Path) -> Path | None:
        self._progress("texturing", 90, "Texturing the mesh with OpenMVS")
        textured = self.work / "scene_dense_mesh_texture.glb"
        try:
            self._run(
                "TextureMesh",
                [
                    "--working-folder",
                    str(self.work),
                    "--input-file",
                    str(self.work / "scene_dense.mvs"),
                    "--mesh-file",
                    str(mesh_ply),
                    "--output-file",
                    str(textured),
                    "--export-type",
                    "glb",
                    "--max-threads",
                    str(self.max_threads),
                    "--resolution-level",
                    str(self.texture_resolution_level),
                ],
                "texturing.log",
            )
        except RuntimeError:
            try:
                obj = self.work / "scene_dense_mesh_texture.obj"
                self._run(
                    "TextureMesh",
                    [
                        "--working-folder",
                        str(self.work),
                        "--input-file",
                        str(self.work / "scene_dense.mvs"),
                        "--mesh-file",
                        str(mesh_ply),
                        "--output-file",
                        str(obj),
                        "--export-type",
                        "obj",
                        "--max-threads",
                        str(self.max_threads),
                    ],
                    "texturing.log",
                )
                return obj if obj.exists() else None
            except RuntimeError:
                return None
        return textured if textured.exists() else None

    def validate_cloud(self, ply: Path) -> tuple[Path, dict]:
        xyz, rgb, _ = read_ply(ply)
        xyz, rgb = statistical_filter(xyz, rgb)
        report = validate_dense(xyz)
        if not report["ok"]:
            raise RuntimeError(
                "Reconstruction failed quality validation. " + report["message"]
            )
        from backend.pipeline.export.ply import write_ascii_ply

        cleaned = self.work / "dense_clean.ply"
        write_ascii_ply(cleaned, xyz, rgb=rgb)
        return cleaned, {**report, "densePoints": int(len(xyz))}

    def validate_mesh_file(self, ply: Path, cloud: Path) -> tuple[object, object, object, dict]:
        from backend.pipeline.reconstruct.colmap.parser import color_mesh_from_cloud

        xyz, rgb, faces = read_ply(ply)
        cloud_xyz, cloud_rgb, _ = read_ply(cloud)
        if len(rgb) != len(xyz) or (rgb == 180).all():
            rgb = color_mesh_from_cloud(xyz, cloud_xyz, cloud_rgb)
        report = validate_mesh(xyz, faces)
        if not report["ok"]:
            raise RuntimeError(
                "Reconstruction failed quality validation. " + report["message"]
            )
        return xyz, rgb, faces, report
