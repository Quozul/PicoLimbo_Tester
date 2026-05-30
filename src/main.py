"""FastAPI application for the PicoLimbo Build API."""

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import database
from .builder import engine, worker
from .models import JobCreate, JobInfo, TestResult
from .orchestration import job_runner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PicoLimbo Build API",
    description="Build and test PicoLimbo against Minecraft versions on demand.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Start the build queue worker on startup
app.state.queue_thread = worker.start_queue_worker()


@app.get("/health")
def health_check():
    """Liveness check."""
    return {"status": "ok"}


@app.post(
    "/jobs",
    response_model=JobInfo,
    status_code=201,
    summary="Create a build and test job",
)
def create_job(body: JobCreate):
    """Create a new job.

    Always creates a new job. Step-level logic handles skipping/reusing:
    - Repo: updates existing clone
    - Build: reuses artifact if already built for this commit hash
    - Tests: skips versions already tested for this commit hash
    """
    try:
        job = engine.create_job(body.repo_url, body.ref, body.versions)
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
    job = database.get_job_by_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Compute ETA if in testing phase
    eta = job_runner._compute_eta(job)

    # Build response
    response = dict(job)
    response["test_results"] = {
        k: TestResult(
            version=v.get("version", k),
            passed=v.get("passed", False),
            screenshot_path=v.get("screenshot_path"),
            duration_seconds=v.get("duration_seconds"),
            error=v.get("error"),
        )
        for k, v in (job.get("test_results") or {}).items()
    }
    response["eta_seconds"] = eta
    return response


@app.get(
    "/jobs/{job_id}/artifact",
    summary="Download build artifact",
)
def get_artifact(job_id: str):
    """Download the built artifact binary.

    Returns 404 if the job does not exist or the artifact is not yet built.
    """
    artifact_path = engine.get_artifact_file(job_id)
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
    "/jobs/{job_id}/screenshots",
    summary="List screenshots for a job",
)
def list_screenshots(job_id: str):
    """List all screenshots taken during testing for this job.

    Returns 404 if the job does not exist.
    """
    job = database.get_job_by_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    test_results = job.get("test_results") or {}
    screenshots = []
    for version, result in test_results.items():
        if result.get("screenshot_path"):
            screenshots.append({
                "screenshot_id": version,
                "version": version,
                "path": result["screenshot_path"],
                "passed": result.get("passed", False),
            })

    return screenshots


@app.get(
    "/jobs/{job_id}/screenshots/{screenshot_id}",
    summary="Download a specific screenshot",
)
def get_screenshot(job_id: str, screenshot_id: str):
    """Download a specific screenshot by version (screenshot_id = version string).

    Returns 404 if the job or screenshot does not exist.
    """
    job = database.get_job_by_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    test_results = job.get("test_results") or {}
    result = test_results.get(screenshot_id)
    if not result or not result.get("screenshot_path"):
        raise HTTPException(status_code=404, detail="Screenshot not found")

    screenshot_path = Path(result["screenshot_path"])
    if not screenshot_path.exists():
        raise HTTPException(status_code=404, detail="Screenshot file not found on disk")

    return FileResponse(
        path=str(screenshot_path),
        media_type="image/png",
        filename=f"{screenshot_id}.png",
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

    - `status`: filter by status (queued, building, testing, finished, failed)
    - `limit`: max number of results (default 100)
    """
    jobs = database.list_jobs(status=status, limit=limit)

    # Compute ETA for each job in testing phase
    result = []
    for job in jobs:
        eta = job_runner._compute_eta(job)
        response = dict(job)
        response["test_results"] = {
            k: TestResult(
                version=v.get("version", k),
                passed=v.get("passed", False),
                screenshot_path=v.get("screenshot_path"),
                duration_seconds=v.get("duration_seconds"),
                error=v.get("error"),
            )
            for k, v in (job.get("test_results") or {}).items()
        }
        response["eta_seconds"] = eta
        result.append(response)

    return result


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
    job = database.get_job_by_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] in ("queued", "building", "testing"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry job with status '{job['status']}'",
        )

    updated = database.update_job(job_id, status="queued", current_step=None)
    return updated
