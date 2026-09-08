"""Optional LingBot-Map backend.

LingBot-Map (https://github.com/Robbyant/lingbot-map) is a feed-forward
streaming 3D reconstruction model. It is the right class of method for
SIH 26158 (single-pass video → 3D), but it needs:

  - Python 3.10+
  - NVIDIA GPU + CUDA (official install uses PyTorch 2.8 + cu128)
  - The published checkpoint from Hugging Face `robbyant/lingbot-map`

This Mac / CPU demo cannot run it. When those deps exist, set
LINGBOT_MODEL=/path/to/lingbot-map.pt and we will prefer it over ORB/VO.
"""

from __future__ import annotations

import os
from pathlib import Path


def lingbot_available() -> bool:
    if not os.environ.get("LINGBOT_MODEL"):
        return False
    try:
        import torch  # noqa: F401
    except ImportError:
        return False
    return Path(os.environ["LINGBOT_MODEL"]).exists()


def reconstruct_with_lingbot(frame_paths: list[Path]) -> None:
    """Placeholder for a CUDA box. Raises a clear error until wired to demo.py APIs."""
    raise RuntimeError(
        "LingBot-Map is not installed in this environment. "
        "It needs Python 3.10, an NVIDIA GPU, and the official checkpoint. "
        "See https://github.com/Robbyant/lingbot-map — then set LINGBOT_MODEL."
    )
