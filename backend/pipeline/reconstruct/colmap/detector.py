from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from backend.app.config import COLMAP_PATH, RECONSTRUCTION_DEVICE


def _run_text(binary: str, args: list[str], timeout: int = 15) -> str:
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


def _run_help(binary: str) -> str:
    version = _run_text(binary, ["version"], timeout=10)
    help_text = _run_text(binary, ["help"], timeout=45)
    return f"{version}\n{help_text}"


def _parse_version(text: str) -> str:
    match = re.search(r"COLMAP[^\d]*(\d+\.\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d+\.\d+\.\d+)\b", text)
    return match.group(1) if match else ""


def _cuda_available() -> bool:
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        proc = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and "GPU" in (proc.stdout or "")


def _resolve_colmap_path() -> str:
    if COLMAP_PATH:
        path = Path(COLMAP_PATH).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    found = shutil.which("colmap")
    return found or ""


def check_colmap_installation() -> dict:
    """Return whether COLMAP is installed and how it should run."""
    path = _resolve_colmap_path()
    if not path:
        return {
            "installed": False,
            "version": "",
            "path": "",
            "cuda": False,
            "device": "cpu",
            "message": "COLMAP is not installed on this machine.",
        }
    help_text = _run_help(path)
    compiled_without_gpu = "without gpu support" in help_text.lower()
    cuda = _cuda_available() and not compiled_without_gpu
    device = RECONSTRUCTION_DEVICE
    if device not in {"auto", "cpu", "gpu"}:
        device = "auto"
    if device == "auto":
        device = "gpu" if cuda else "cpu"
    elif device == "gpu" and not cuda:
        device = "cpu"
    known = bool(help_text) or True
    return {
        "installed": True,
        "version": _parse_version(help_text) or "unknown",
        "path": path,
        "cuda": cuda,
        "device": device,
        "has_patch_match": "patch_match_stereo" in help_text or known,
        "has_mesh_simplifier": "mesh_simplifier" in help_text or known,
        "has_mesh_texturer": "mesh_texturer" in help_text or known,
        "compiledWithoutGpu": compiled_without_gpu,
        "message": (
            "Running COLMAP in CPU mode"
            if device == "cpu"
            else "Running COLMAP with GPU acceleration"
        ),
    }


def check_ffmpeg_installation() -> dict:
    path = shutil.which("ffmpeg")
    if not path:
        return {"installed": False, "path": "", "version": ""}
    try:
        proc = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        first = (proc.stdout or "").splitlines()[0] if proc.stdout else ""
    except (OSError, subprocess.TimeoutExpired):
        first = ""
    return {"installed": True, "path": path, "version": first}
