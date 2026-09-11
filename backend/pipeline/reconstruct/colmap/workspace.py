from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.config import RECONSTRUCTION_DEBUG


STAGES = (
    "frameExtraction",
    "frameSelection",
    "featureExtraction",
    "matching",
    "sfm",
    "sparseValidation",
    "undistortion",
    "mvs",
    "fusion",
    "denseValidation",
    "meshing",
    "refinement",
    "texturing",
    "glb",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ColmapWorkspace:
    def __init__(self, job_root: Path):
        self.root = Path(job_root)
        self.input = self.root / "input"
        self.frames = self.root / "work" / "frames"
        self.images = self.root / "images"
        self.sparse = self.root / "sparse"
        self.dense = self.root / "dense"
        self.openmvs = self.root / "openmvs"
        self.mesh = self.root / "mesh"
        self.textures = self.root / "textures"
        self.output = self.root / "output"
        self.logs = self.root / "logs"
        self.state_path = self.root / "job_state.json"
        self.database = self.root / "database.db"
        self.metadata_path = self.root / "metadata.json"
        self.quality_path = self.output / "quality.json"

    def create(self) -> None:
        for path in (
            self.input,
            self.frames,
            self.images,
            self.sparse,
            self.dense,
            self.openmvs,
            self.mesh,
            self.textures,
            self.output,
            self.logs,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not self.metadata_path.exists():
            self.save_metadata(
                {
                    "created_at": utc_now(),
                    "stages": {name: "pending" for name in STAGES},
                    "metrics": {},
                    "device": "",
                    "pipeline": "COLMAP SfM + MVS + Poisson",
                }
            )

    def load_metadata(self) -> dict[str, Any]:
        if not self.metadata_path.exists():
            return {"stages": {name: "pending" for name in STAGES}, "metrics": {}}
        return json.loads(self.metadata_path.read_text(encoding="utf-8"))

    def save_metadata(self, data: dict[str, Any]) -> None:
        data["updated_at"] = utc_now()
        tmp = self.metadata_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.metadata_path)

    def set_stage(self, name: str, status: str, **extra: Any) -> dict[str, Any]:
        meta = self.load_metadata()
        stages = meta.setdefault("stages", {})
        stages[name] = status
        if extra:
            meta.setdefault("metrics", {}).update(extra)
        self.save_metadata(meta)
        return meta

    def stage_done(self, name: str) -> bool:
        return self.load_metadata().get("stages", {}).get(name) == "completed"

    def write_quality(self, payload: dict[str, Any]) -> Path:
        self.output.mkdir(parents=True, exist_ok=True)
        self.quality_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.quality_path

    def cleanup_intermediates(self) -> None:
        if RECONSTRUCTION_DEBUG:
            return
        stereo = self.dense / "stereo"
        undistorted = self.dense / "images"
        for path in (stereo, undistorted):
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
