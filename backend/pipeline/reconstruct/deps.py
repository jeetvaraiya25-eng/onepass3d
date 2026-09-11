from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from backend.app.config import COLMAP_PATH, FFMPEG_PATH, OPENMVS_PATH, ROOT_DIR
from backend.pipeline.reconstruct.colmap.detector import check_colmap_installation


OPENMVS_BINARIES = (
    "InterfaceCOLMAP",
    "DensifyPointCloud",
    "ReconstructMesh",
    "RefineMesh",
    "TextureMesh",
)


def _run(binary: str, args: list[str], timeout: int = 12) -> str:
    try:
        proc = subprocess.run(
            [binary, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()


def _resolve_env_or_which(env_value: str, name: str) -> str:
    if env_value:
        path = Path(env_value).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        if path.is_dir():
            candidate = path / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    found = shutil.which(name)
    return found or ""


def check_ffmpeg_installation() -> dict:
    path = _resolve_env_or_which(FFMPEG_PATH, "ffmpeg")
    if not path:
        return {"installed": False, "path": "", "version": ""}
    text = _run(path, ["-version"])
    first = text.splitlines()[0] if text else ""
    return {"installed": True, "path": path, "version": first}


def _bundled_openmvs_dir() -> Path:
    return ROOT_DIR / "tools" / "openmvs"


def _openmvs_dir() -> Path | None:
    if OPENMVS_PATH:
        path = Path(OPENMVS_PATH).expanduser()
        if path.is_file():
            return path.parent
        if path.is_dir() and (path / "DensifyPointCloud").exists():
            return path
    bundled = _bundled_openmvs_dir()
    if (bundled / "DensifyPointCloud").exists():
        return bundled
    found = shutil.which("DensifyPointCloud")
    if found:
        return Path(found).parent
    return None


def check_openmvs_installation() -> dict:
    folder = _openmvs_dir()
    if folder is None:
        return {
            "installed": False,
            "path": "",
            "version": "",
            "binaries": {},
            "message": "OpenMVS is not installed on this machine.",
        }
    binaries = {}
    for name in OPENMVS_BINARIES:
        exe = folder / name
        binaries[name] = str(exe) if exe.is_file() else ""
    missing = [name for name, path in binaries.items() if not path]
    version = ""
    densify = binaries.get("DensifyPointCloud")
    if densify:
        text = _run(densify, ["-h"])
        match = re.search(r"OpenMVS[^\d]*v?(\d+\.\d+\.\d+)", text)
        version = match.group(1) if match else ""
    return {
        "installed": not missing,
        "path": str(folder),
        "version": version or "unknown",
        "binaries": binaries,
        "missing": missing,
        "message": (
            "OpenMVS ready for local CPU dense reconstruction"
            if not missing
            else f"OpenMVS is incomplete. Missing: {', '.join(missing)}"
        ),
    }


def check_dependencies() -> dict:
    colmap = check_colmap_installation()
    ffmpeg = check_ffmpeg_installation()
    openmvs = check_openmvs_installation()
    dense = "colmap" if colmap.get("cuda") else ("openmvs" if openmvs.get("installed") else "unavailable")
    return {
        "ffmpeg": ffmpeg,
        "colmap": colmap,
        "openmvs": openmvs,
        "denseBackend": dense,
    }
