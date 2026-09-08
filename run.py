#!/usr/bin/env python3
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import uvicorn


def pick_port(preferred: int = 8000) -> int:
    for port in range(preferred, preferred + 12):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            in_use = sock.connect_ex(("127.0.0.1", port)) == 0
        if not in_use:
            return port
    return preferred + 12


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or os.environ.get("ONEPASS_PORT") or "0") or pick_port()
    hosted = bool(os.environ.get("PORT") or os.environ.get("RENDER") or os.environ.get("RAILWAY_ENVIRONMENT"))
    host = "0.0.0.0" if hosted else "127.0.0.1"
    print(f"OnePass3D → http://{host}:{port}", flush=True)
    uvicorn.run(
        "backend.app.main:app",
        host=host,
        port=port,
        reload=False,
    )
