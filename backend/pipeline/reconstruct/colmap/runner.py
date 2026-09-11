from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from backend.app.config import COLMAP_STAGE_TIMEOUT


ProgressFn = Callable[[str], None]


class ColmapCancelled(RuntimeError):
    pass


class ColmapTimeout(RuntimeError):
    pass


class ColmapRunner:
    """Spawn COLMAP with argument arrays. Never concatenates user input into a shell."""

    def __init__(self, binary: str, logs_dir: Path, cancel_event: threading.Event | None = None):
        self.binary = binary
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.cancel_event = cancel_event or threading.Event()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.kill()

    def kill(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            if sys.platform == "win32":
                proc.terminate()
            else:
                os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            return
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                if sys.platform == "win32":
                    proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass

    def run(
        self,
        args: list[str],
        log_name: str,
        timeout: int | None = None,
        on_progress: ProgressFn | None = None,
        binary: str | None = None,
    ) -> dict:
        if self.cancel_event.is_set():
            raise ColmapCancelled("Reconstruction was cancelled.")
        command = [binary or self.binary, *args]
        log_path = self.logs_dir / log_name
        started = time.time()
        creationflags = 0
        preexec = None
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            preexec = os.setsid
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            log.write("COMMAND " + " ".join(command) + "\n\n")
            log.flush()
            try:
                proc = subprocess.Popen(
                    command,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=creationflags,
                    preexec_fn=preexec,
                )
            except FileNotFoundError as exc:
                raise RuntimeError("COLMAP is not installed on this machine.") from exc
            with self._lock:
                self._proc = proc
            limit = timeout or COLMAP_STAGE_TIMEOUT
            deadline = started + limit
            while proc.poll() is None:
                if self.cancel_event.is_set():
                    self.kill()
                    raise ColmapCancelled("Reconstruction was cancelled.")
                if time.time() > deadline:
                    self.kill()
                    raise ColmapTimeout(f"COLMAP stage timed out after {limit}s: {args[0] if args else 'colmap'}")
                if on_progress:
                    on_progress(args[0] if args else "colmap")
                time.sleep(0.4)
            code = int(proc.returncode or 0)
        with self._lock:
            self._proc = None
        result = {
            "success": code == 0,
            "command": command,
            "exitCode": code,
            "duration": time.time() - started,
            "logPath": str(log_path),
        }
        if code != 0:
            tail = _tail(log_path)
            result["error"] = tail
            raise RuntimeError(_friendly_colmap_error(args, tail, code))
        return result


def _tail(path: Path, lines: int = 40) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def _friendly_colmap_error(args: list[str], tail: str, code: int) -> str:
    stage = args[0] if args else "COLMAP"
    lower = tail.lower()
    if "cuda" in lower and ("not available" in lower or "no device" in lower or "cannot" in lower):
        return (
            "COLMAP PatchMatch dense stereo needs a CUDA GPU. "
            "This machine is running in CPU mode, so dense reconstruction cannot continue."
        )
    if "out of memory" in lower or "std::bad_alloc" in lower:
        return f"COLMAP ran out of memory during {stage}."
    if "no valid" in lower or "failed to reconstruct" in lower:
        return f"COLMAP {stage} could not reconstruct a connected camera model from these frames."
    snippet = " ".join(tail.split())
    if len(snippet) > 280:
        snippet = snippet[:277] + "..."
    if snippet:
        return f"COLMAP {stage} failed (exit {code}): {snippet}"
    return f"COLMAP {stage} failed with exit code {code}."
