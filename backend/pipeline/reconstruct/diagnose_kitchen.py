"""Print SfM connectivity for the existing kitchen keyframes. No meshing."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from backend.pipeline.reconstruct.diagnostics import contiguous_runs, trajectory_is_connected
from backend.pipeline.reconstruct.sfm import incremental_sfm, assess_poses


def main() -> None:
    root = Path("data/jobs/77e7c09bf790/work/frames")
    frames = [cv2.imread(str(p)) for p in sorted(root.glob("frame_*.jpg"))]
    print("selected_on_disk", len(frames), "shape", None if not frames else frames[0].shape)
    sfm = incremental_sfm(frames)
    ok, why, diag = trajectory_is_connected(sfm.registered)
    print("registered", int(sfm.registered.sum()), "/", len(frames))
    print("indices", np.where(sfm.registered)[0].tolist())
    print("runs", contiguous_runs(sfm.registered))
    print("connected", ok, why)
    print("reproj", sfm.stats.median_reproj, "sparse", sfm.stats.sparse_points)
    print("fx_fy", float(sfm.pose.K[0, 0]), float(sfm.pose.K[1, 1]))
    if ok:
        print("assess", assess_poses(sfm))
    else:
        print("STOP: not proceeding to MVS")


if __name__ == "__main__":
    main()
