from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_report(output_dir: Path, payload: dict[str, Any]) -> Path:
    path = output_dir / "report.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
