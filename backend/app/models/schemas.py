from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class JobProgress(BaseModel):
    stage: str = "queued"
    percent: int = 0
    message: str = "Waiting to start"


class JobSummary(BaseModel):
    id: str
    name: str
    status: str
    created_at: str
    updated_at: str
    progress: JobProgress
    error: Optional[str] = None
    has_gps: bool = False
    frame_count: int = 0
    point_count: int = 0
    triangle_count: int = 0
    metric: bool = False


class JobDetail(JobSummary):
    input_files: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    result: Optional[dict[str, Any]] = None
    quality: Optional[str] = None


class JobList(BaseModel):
    jobs: list[JobSummary]
