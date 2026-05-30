"""Pydantic models for the PicoLimbo Build API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    """Request body for POST /jobs."""

    repo_url: Optional[str] = Field(
        default="https://github.com/Quozul/PicoLimbo.git",
        description="GitHub repository URL (must be github.com)",
    )
    ref: Optional[str] = Field(
        default="master",
        description="Branch name or commit hash",
    )


class JobInfo(BaseModel):
    """Shared response model for job information."""

    job_id: str
    status: str  # "queued", "building", "finished", "failed"
    repo_url: str
    ref: str
    owner: str
    commit_hash: str
    artifact_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime
