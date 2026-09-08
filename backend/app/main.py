from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from contextlib import asynccontextmanager

from backend.app.api.jobs import router as jobs_router
from backend.app.config import DATA_DIR, FRONTEND_DIR
from backend.pipeline.demo.real_splat import publish_frontend_samples


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        publish_frontend_samples()
    except Exception as exc:
        print(f"Sample scenes not ready yet: {exc}", flush=True)
    yield


app = FastAPI(
    title="OnePass3D",
    description="Single-pass drone video to georeferenced 3D models",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(jobs_router)


@app.middleware("http")
async def no_cache_ui(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-store"
    elif path.endswith(".splat"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@app.get("/api")
def root() -> dict:
    return {"name": "OnePass3D", "docs": "/docs"}


_sample_dir = DATA_DIR / "sample"
if _sample_dir.exists():
    app.mount("/sample-data", StaticFiles(directory=str(_sample_dir)), name="sample-data")

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
