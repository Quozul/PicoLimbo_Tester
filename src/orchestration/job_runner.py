"""Job runner — thin wrapper around JobOrchestrator.

Preserves the legacy run_job(job_id) function signature and module-level
helper functions for backward compatibility.  All logic is delegated to
:class:`JobOrchestrator` which uses injected domain services.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .. import config
from .. import database
from ..builder import engine
from ..domain.job import Job
from ..infrastructure.artifact_repository import ArtifactRepository
from ..infrastructure.artifact_storage import ArtifactStorage
from ..infrastructure.config_writer import ConfigWriter
from ..minecraft.env import create_servers_dat
from ..minecraft.input import VirtualInputController
from ..minecraft.runner import empty_directory, test_single_version
from ..proxy import get_proxy_manager
from ..proxy.factory import ProxyFactory
from .job_orchestrator import JobOrchestrator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Legacy constants — kept for backward compatibility with existing tests
# ---------------------------------------------------------------------------

SCREENSHOTS_DIR = config.SCREENSHOTS_DIR


def _make_orchestrator() -> JobOrchestrator:
    """Create a JobOrchestrator with default dependencies."""
    return JobOrchestrator(
        builds_dir=config.BUILDS_DIR,
        proxy_factory=ProxyFactory(ConfigWriter()),
        config_writer=ConfigWriter(),
        artifact_repo=ArtifactRepository(
            api_base=config.VELOCITY_API_BASE,
            cache_dir=config.PROXY_CACHE_DIR / "velocity",
        ),
        game_directory=config.GAME_DIRECTORY,
        screenshots_dir=config.SCREENSHOTS_DIR,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_job(job_id: str) -> None:
    """Run all steps for a job.

    Thin wrapper that creates a :class:`JobOrchestrator` and delegates to it.
    Calls module-level wrapper functions (which delegate to the orchestrator's
    private methods) so that existing tests can patch them.
    """
    job = database.get_job_by_id(job_id)
    if not job:
        logger.error("Job %s not found", job_id)
        return

    versions = job.get("versions") or []
    if not versions:
        from ..versions import ALL_VERSIONS

        versions = [str(v) for v in ALL_VERSIONS]
        database.update_job(job_id, versions=json.dumps(versions))

    proxy_type = job.get("proxy", "none") or "none"
    logger.info("Job %s: proxy_type=%r", job_id, proxy_type)

    proxy_proc: Optional[subprocess.Popen] = None
    pico_limbo_proc: Optional[subprocess.Popen] = None

    try:
        # Build step
        _update_job(job_id, status="building", current_step="building")
        skipped, artifact_path = _build_step(job)
        if skipped:
            logger.info("Job %s: build skipped (artifact already exists)", job_id)
        else:
            logger.info("Job %s: build completed", job_id)
        _update_job(
            job_id,
            status="testing",
            current_step="testing",
            artifact_path=artifact_path,
        )

        # Re-fetch job in case artifact_path was just set
        job = database.get_job_by_id(job_id)
        proxy_proc, pico_limbo_proc = _server_step(job, versions, proxy_type)

        # Test step
        _update_job(job_id, current_step="testing")
        job = database.get_job_by_id(job_id)
        test_results = _test_step(job, versions, pico_limbo_proc)

        # Done
        _update_job(
            job_id,
            status="finished",
            current_step="finished",
            test_results=json.dumps(test_results),
            eta_seconds=0,
        )

        logger.info("Job %s finished successfully", job_id)

    except Exception as e:
        logger.exception("Job %s failed", job_id)
        _update_job(
            job_id,
            status="failed",
            error_message=str(e),
        )
    finally:
        _kill_server(proxy_proc, pico_limbo_proc)


# ---------------------------------------------------------------------------
# Module-level wrappers — kept for backward compatibility with existing tests
# These delegate to JobOrchestrator's private methods.
# ---------------------------------------------------------------------------


def _build_step(job: dict) -> tuple[bool, str]:
    """Execute the build step.

    Checks for existing artifacts first; if none found, clones the repo,
    resolves the commit, and builds using :func:`src.builder.engine.build_project`.

    Parameters
    ----------
    job : dict
        Job dictionary from the database.

    Returns
    -------
    tuple[bool, str]
        (skipped, artifact_path).
    """
    job_id = job["job_id"]
    owner = job["owner"]
    repo_name = job["repo_url"].split("/")[-1].replace(".git", "")
    ref = job["ref"]
    commit_hash = job["commit_hash"]

    # Check if artifact already exists for this commit hash
    storage = ArtifactStorage(engine.BUILDS_DIR)
    existing = storage.get(commit_hash)
    if existing:
        logger.info("Job %s: artifact already exists, skipping build", job_id)
        return True, str(existing)

    # Re-resolve commit in case it changed (branch moved)
    repo_path = engine._get_git_repo().clone(owner, repo_name)
    commit_hash = engine._get_git_repo().resolve(repo_path, ref)
    database.update_job(job_id, commit_hash=commit_hash)

    # Build using BuildService
    result = engine.build_project(job["repo_url"], ref, owner, repo_name)

    # Update job with artifact path
    database.update_job(job_id, artifact_path=str(result.artifact_path.value))
    logger.info("Job %s: build completed, artifact=%s", job_id, result.artifact_path.value)

    return False, str(result.artifact_path.value)


def _server_step(
    job: dict, versions: list[str], proxy_type: str = "none"
) -> tuple[Optional[subprocess.Popen], Optional[subprocess.Popen]]:
    """Start proxy (if any) and PicoLimbo server, then wait for them to be ready.

    Thin wrapper around JobOrchestrator._run_server_setup().

    Parameters
    ----------
    job : dict
        Job dictionary from the database.
    versions : list[str]
        Minecraft versions to test (unused, kept for API compatibility).
    proxy_type : str
        Proxy type (e.g. "velocity", "none").

    Returns
    -------
    tuple[Optional[subprocess.Popen], Optional[subprocess.Popen]]
        (proxy_process, pico_limbo_process).
    """
    job_id = job["job_id"]
    artifact_path = job.get("artifact_path")
    if not artifact_path:
        raise RuntimeError("No artifact path for job")

    orchestrator = _make_orchestrator()
    job_obj = Job.from_dict(job)
    server_context = orchestrator._run_server_setup(job_obj, proxy_type)

    proxy_proc: Optional[subprocess.Popen] = None
    pico_limbo_proc: Optional[subprocess.Popen] = None

    if server_context.proxy_proc is not None:
        proxy_proc = server_context.proxy_proc
    if server_context.pico_limbo_proc is not None:
        pico_limbo_proc = server_context.pico_limbo_proc

    return proxy_proc, pico_limbo_proc


def _test_step(
    job: dict,
    versions: list[str],
    server_proc: Optional[subprocess.Popen],
) -> dict:
    """Run Minecraft tests for all versions.

    Thin wrapper around JobOrchestrator._run_tests().

    Parameters
    ----------
    job : dict
        Job dictionary from the database.
    versions : list[str]
        Minecraft versions to test.
    server_proc : Optional[subprocess.Popen]
        The server process (unused; kept for API compatibility).

    Returns
    -------
    dict
        Updated test_results dict.
    """
    job_id = job["job_id"]
    commit_hash = job["commit_hash"]
    test_results = dict(job.get("test_results") or {})

    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    empty_directory(str(config.GAME_DIRECTORY / "screenshots"))

    virtual_device = VirtualInputController()

    try:
        login_wait_timeout = job.get("login_wait_timeout", 30)
        for version in versions:
            current = database.get_job_by_id(job_id)
            if current and current["status"] == "cancelled":
                database.update_job(job_id, status="failed", error_message="Job was cancelled")
                return test_results
            logger.info("Job %s: testing version %s", job_id, version)
            _update_job(job_id, current_step=f"testing:{version}")
            result = test_single_version(version, commit_hash, virtual_device, SCREENSHOTS_DIR, login_wait_timeout)
            test_results[version] = result

            # Persist after each version so we don't lose progress
            database.update_job(
                job_id,
                test_results=json.dumps(test_results),
            )

    except Exception as e:
        _update_job(job_id, status="failed", error_message=str(e))
        raise
    finally:
        _kill_server(None, server_proc)

    return test_results


def _kill_server(
    proxy_proc: Optional[subprocess.Popen], pico_limbo_proc: Optional[subprocess.Popen]
) -> None:
    """Kill the PicoLimbo server and proxy processes if running.

    Parameters
    ----------
    proxy_proc : Optional[subprocess.Popen]
        The proxy process.
    pico_limbo_proc : Optional[subprocess.Popen]
        The PicoLimbo process.
    """
    # Kill PicoLimbo first
    if pico_limbo_proc and pico_limbo_proc.poll() is None:
        logger.info("Killing PicoLimbo server")
        pico_limbo_proc.kill()
        try:
            pico_limbo_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("PicoLimbo did not terminate, forcing")
            pico_limbo_proc.kill()

    # Then kill the proxy (if any)
    if proxy_proc and proxy_proc.poll() is None:
        logger.info("Killing proxy")
        proxy_proc.kill()
        try:
            proxy_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Proxy did not terminate, forcing")
            proxy_proc.kill()


def _update_job(job_id: str, **fields: Any) -> dict:
    """Update job and refresh with ETA if in testing phase.

    Directly calls database.update_job (patchable by tests) and computes
    ETA via the orchestrator when the job enters the testing phase.

    Parameters
    ----------
    job_id : str
        The job identifier.
    **fields : Any
        Fields to update.

    Returns
    -------
    dict
        The updated job dictionary.
    """
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    database.update_job(job_id, **fields)

    # Compute and update ETA if in testing phase
    if fields.get("status") == "testing":
        job = database.get_job_by_id(job_id)
        if job:
            eta = _compute_eta(job)
            if eta is not None:
                database.update_job(job_id, eta_seconds=eta)

    return database.get_job_by_id(job_id)


def _compute_eta(job: dict) -> Optional[int]:
    """Compute ETA in seconds based on test progress.

    Thin wrapper around the orchestrator's _compute_eta.

    Parameters
    ----------
    job : dict
        Job dictionary from the database.

    Returns
    -------
    Optional[int]
        ETA in seconds, or None if it cannot be computed.
    """
    orchestrator = _make_orchestrator()
    return orchestrator._compute_eta(job)
