"""FastAPI application for the PicoLimbo Build API."""

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

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
        job = engine.create_job(
            body.repo_url, body.ref, body.versions, body.proxy,
            body.forwarding_method, plugins=body.plugins,
            login_wait_timeout=body.login_wait_timeout,
        )
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


# ─── Plugin Endpoints ────────────────────────────────────────────────────────

PLUGINS_DIR = Path("/app/plugins")


def _ensure_plugins_dir() -> None:
    """Ensure the plugins directory exists."""
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)


@app.post(
    "/plugins/upload",
    status_code=201,
    summary="Upload a Velocity plugin (.jar file)",
)
async def upload_plugin(plugin: UploadFile = File(...)):
    """Upload a Velocity plugin .jar file.

    Saves the file to the plugins directory and returns its name.
    """
    _ensure_plugins_dir()

    if not plugin.filename or not plugin.filename.endswith(".jar"):
        raise HTTPException(
            status_code=400,
            detail="Only .jar files are allowed",
        )

    file_path = PLUGINS_DIR / plugin.filename

    # Read and save the file
    content = await plugin.read()
    file_path.write_bytes(content)

    return {"name": plugin.filename, "status": "ready"}


@app.get(
    "/plugins",
    summary="List all uploaded plugins",
)
def list_plugins():
    """List all uploaded plugin .jar files."""
    _ensure_plugins_dir()

    plugins = []
    for path in sorted(PLUGINS_DIR.iterdir()):
        if path.is_file() and path.suffix == ".jar":
            plugins.append({"name": path.name, "status": "ready"})

    return plugins


@app.delete(
    "/plugins/{name}",
    summary="Delete an uploaded plugin",
)
def delete_plugin(name: str):
    """Delete an uploaded plugin .jar file.

    Returns 404 if the plugin does not exist.
    """
    safe_name = Path(name).name  # Sanitize against path traversal
    file_path = PLUGINS_DIR / safe_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Plugin not found")

    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    file_path.unlink()
    return {"deleted": True}


# ─── Serve embedded webui ──────────────────────────────────────────────────────

WEBUI_DIR = Path(__file__).parent.parent / "webui-dist"

# Serve static assets (JS, CSS, fonts)
app.mount("/assets", StaticFiles(directory=str(WEBUI_DIR / "assets")), name="assets")


@app.get("/favicon.ico", include_in_schema=False)
async def serve_favicon():
    """Serve the Vite favicon."""
    favicon = WEBUI_DIR / "vite.svg"
    if favicon.exists():
        return FileResponse(str(favicon), media_type="image/svg+xml")
    return Response(status_code=404)


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    """Serve the React SPA for any non-API route."""
    # Let API routes handle these
    if full_path.startswith("api/"):
        return Response(status_code=404)

    # Serve exact files if they exist (for assets loaded by the SPA)
    file_path = WEBUI_DIR / full_path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))

    # Fall back to index.html for SPA routing
    index_path = WEBUI_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return Response(status_code=404, content="Not found")


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
