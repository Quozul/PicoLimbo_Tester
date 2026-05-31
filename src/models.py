"""Pydantic models for the PicoLimbo Build API."""

from datetime import datetime
from typing import Any, Optional

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
    versions: Optional[list[str]] = Field(
        default=None,
        description="List of Minecraft versions to test (default: all versions)",
    )
    proxy: str = Field(
        default="none",
        description="Proxy type: none, velocity, bungeecord",
    )
    forwarding_method: str = Field(
        default="modern",
        description="Velocity player-info-forwarding-mode: none, legacy, bungeeguard, modern",
    )
    forwarding_secret: str = Field(
        default="sup3r-s3cr3t",
        description="Velocity forwarding secret file content",
    )


class TestResult(BaseModel):
    """Result of testing a single Minecraft version."""
    version: str
    passed: bool
    screenshot_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None


class JobInfo(BaseModel):
    """Shared response model for job information."""

    job_id: str
    status: str  # "queued", "building", "testing", "finished", "failed"
    repo_url: str
    ref: str
    owner: str
    commit_hash: str
    current_step: Optional[str] = None
    versions: list[str] = []
    test_results: dict[str, TestResult] = {}
    artifact_path: Optional[str] = None
    error_message: Optional[str] = None
    eta_seconds: Optional[int] = None
    created_at: datetime
    updated_at: datetime
