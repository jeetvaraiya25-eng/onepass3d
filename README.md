# OnePass3D

Web app that turns a **single-pass drone video or photo set** into a georeferenced 3D model (point cloud, mesh, Gaussian splat file) and inspect it in the browser.

Organization: National Technical Research Organisation (NTRO) · Theme: Robotics and Drones · Category: Software

## What it does

1. You upload a drone video / photos (optional DJI `.srt`, CSV, or GPX).
2. The Python server extracts keyframes, estimates poses, triangulates a cloud, optionally locks scale to GPS, and writes mesh + 3DGS-style Gaussians.
3. The website shows a 3D viewer with measurements, a confidence overlay (observed vs weak geometry), and downloads.

Hidden facades from a single corridor are **not invented**. They stay empty; confidence coloring makes that obvious.

## Run

Python 3.9+ (3.12 recommended). From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

The command prints the URL (usually [http://127.0.0.1:8000](http://127.0.0.1:8000); if that port is taken it uses 8001).

- **Process a flight** — upload video/photos
- **Open sample site** — instant demo scene (metric, occlusions included)

## Project layout

```
backend/
  app/                 FastAPI, job store, workers
  pipeline/
    ingest/            video + keyframe quality
    reconstruct/       poses, triangulation, Gaussians
    geo/               WGS84 → ENU, Umeyama GPS lock
    filters/           moving-object mask
    export/            PLY / OBJ / report
    demo/              sample site
frontend/              website (static, served by FastAPI)
data/jobs/             per-job files
```

API lives under `/api` (see `/docs` when the server is running). The 3D canvas is Three.js in the browser; all reconstruction is Python.

## Inputs

| Required | Optional |
|---|---|
| Video (`mp4`, `mov`, …) or 5+ stills | GPS: `.srt` (DJI), `.csv`, `.gpx` |

CSV columns: `lat`/`latitude`, `lon`/`longitude`, `alt`/`altitude`.

## Outputs

- `pointcloud.ply` — XYZ + RGB + confidence
- `mesh.obj` / `mesh.ply` — 2.5D surface mesh
- `gaussians.ply` — 3D Gaussian Splatting vertex format
- `report.json` — counts, GPS meta, units

## Notes

The live pipeline is a **CPU photogrammetry baseline** (ORB odometry + triangulation + GPS Sim(3)). The Gaussian file is produced from the metric cloud so you can plug in InstantSplat / 2DGS later in `backend/pipeline/reconstruct/` without changing the app.

For a judge demo, start with **Open sample site**, then run a short real clip if you have one.
