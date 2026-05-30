"""FastAPI application for the PicoLimbo Build API."""

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

import database
import pico_limbo_builder
from models import JobCreate, JobInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PicoLimbo Build API",
    description="Build and serve PicoLimbo artifacts on demand.",
    version="0.1.0",
)

# Start the build queue worker on startup
app.state.queue_thread = pico_limbo_builder.start_queue_worker()


@app.get("/health")
def health_check():
    """Liveness check."""
    return {"status": "ok"}


@app.post(
    "/jobs",
    response_model=JobInfo,
    status_code=201,
    summary="Create a build job",
)
def create_job(body: JobCreate):
    """Create a new build job.

    If a job for the same (repo_url, commit_hash) already exists,
    returns the existing job (idempotent).
    """
    try:
        job = pico_limbo_builder.create_or_get_job(body.repo_url, body.ref)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create job")
        raise HTTPException(status_code=500, detail=str(e))

    return job


@app.get(
    "/jobs/{job_id}",
    response_model=JobInfo,
    summary="Get job information",
)
def get_job(job_id: str):
    """Get job information by ID.

    Returns 404 if the job does not exist.
    """
    job = pico_limbo_builder.get_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get(
    "/jobs/{job_id}/artifact",
    summary="Download build artifact",
)
def get_artifact(job_id: str):
    """Download the built artifact binary.

    Returns 404 if the job does not exist or the artifact is not yet built.
    """
    artifact_path = pico_limbo_builder.get_artifact_file(job_id)
    if artifact_path is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")

    return FileResponse(
        path=str(artifact_path),
        media_type="application/octet-stream",
        filename="pico_limbo",
        headers={"Content-Disposition": 'attachment; filename="pico_limbo"'},
    )


@app.get(
    "/jobs",
    response_model=list[JobInfo],
    summary="List all jobs",
)
def list_jobs(
    status: Optional[str] = None,
    limit: int = 100,
):
    """List jobs, optionally filtered by status.

    - `status`: filter by status (queued, building, finished, failed)
    - `limit`: max number of results (default 100)
    """
    return database.list_jobs(status=status, limit=limit)


@app.post(
    "/jobs/{job_id}/retry",
    response_model=JobInfo,
    status_code=200,
    summary="Retry a failed or finished build",
)
def retry_job(job_id: str):
    """Retry a build by resetting its status to 'queued'.

    Only allows retrying jobs with status 'failed' or 'finished'.
    Returns 400 if the job is still queued or building.
    Returns 404 if the job does not exist.
    """
    job = pico_limbo_builder.get_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] in ("queued", "building"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry job with status '{job['status']}'",
        )

    updated = database.update_job(job_id, status="queued")
    return updated
