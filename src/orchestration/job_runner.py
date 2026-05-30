"""Job orchestrator: build → server → tests."""

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import database
from .. import models
from ..builder import engine
from ..minecraft.env import create_servers_dat
from ..minecraft.input import VirtualInputController
from ..minecraft.runner import test_single_version, empty_directory

logger = logging.getLogger(__name__)

# Estimated seconds per Minecraft version test (for ETA calculation)
SECONDS_PER_VERSION = 90

# PicoLimbo config file
SERVER_CONFIG_CONTENT = 'bind = "0.0.0.0:25565"\n'

# servers.dat address (must match server bind)
SERVER_ADDRESS = "127.0.0.1:25565"

# Paths
GAME_DIRECTORY = Path("/app/minecraft")
SCREENSHOTS_DIR = "/app/integration_tests_reports"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_eta(job: dict) -> Optional[int]:
    """Compute ETA in seconds based on test progress.

    Formula: remaining_versions * (total_time_elapsed / tested_versions_count)
    Returns None if we can't compute it (no versions tested yet, or not testing phase).
    """
    status = job["status"]
    if status != "testing":
        return None

    test_results = job.get("test_results") or {}
    tested_count = len(test_results)
    versions = job.get("versions") or []

    if tested_count == 0 or not versions:
        return None

    total_versions = len(versions)
    remaining = total_versions - tested_count
    if remaining <= 0:
        return 0

    created_at = datetime.fromisoformat(job["created_at"])
    elapsed = (datetime.now(timezone.utc) - created_at).total_seconds()

    if elapsed <= 0 or tested_count <= 0:
        return None

    avg_per_version = elapsed / tested_count
    eta = int(remaining * avg_per_version)
    return max(eta, 0)


def _update_job(job_id: str, **fields) -> dict:
    """Update job and refresh with ETA if in testing phase."""
    job = database.update_job(job_id, **fields)
    if job:
        eta = _compute_eta(job)
        if eta is not None:
            database.update_job(job_id, eta_seconds=eta)
        # Re-fetch to get latest
        job = database.get_job_by_id(job_id)
    return job


def _build_step(job: dict) -> tuple[bool, str]:
    """Execute the build step.

    Returns (skipped, artifact_path).
    - skipped=True means artifact already existed, no build needed.
    - artifact_path is always set (either reused or newly built).
    """
    job_id = job["job_id"]
    owner = job["owner"]
    repo_name = job["repo_url"].split("/")[-1].replace(".git", "")
    ref = job["ref"]
    commit_hash = job["commit_hash"]

    repo_path = engine.ensure_repo_cloned(owner, repo_name)
    # Update repo if already cloned (fetch latest)
    engine.update_repo(repo_path, ref)
    # Re-resolve commit in case it changed (branch moved)
    commit_hash = engine.resolve_commit(repo_path, ref)
    database.update_job(job_id, commit_hash=commit_hash)

    # Check if artifact already exists for this commit hash
    artifact_dir = engine.BUILDS_DIR / owner / ref / commit_hash
    artifact_path = artifact_dir / "pico_limbo"
    if artifact_path.exists():
        logger.info("Job %s: artifact already exists, skipping build", job_id)
        return True, str(artifact_path)

    artifact_path_str = engine.build_project(repo_path, commit_hash, owner, ref)
    return False, artifact_path_str


def _server_step(job: dict, versions: list[str]) -> Optional[subprocess.Popen]:
    """Start PicoLimbo server and wait for it to be ready.

    Returns the server process, or None if skipped (all versions already tested).
    """
    job_id = job["job_id"]
    artifact_path = job.get("artifact_path")
    if not artifact_path:
        raise RuntimeError("No artifact path for job")

    # Check if all versions already tested (globally, across all jobs with same commit)
    tested_versions = database.get_tested_versions_for_commit(job["commit_hash"])
    remaining = [v for v in versions if v not in tested_versions]
    if not remaining:
        logger.info("Job %s: all versions already tested, skipping server start", job_id)
        return None

    # Write server config
    config_path = Path("/tmp/server.toml")
    config_path.write_text(SERVER_CONFIG_CONTENT)

    # Write servers.dat
    servers_dat = GAME_DIRECTORY / "servers.dat"
    create_servers_dat(str(servers_dat), SERVER_ADDRESS)

    # Start PicoLimbo
    logger.info("Job %s: starting PicoLimbo server", job_id)
    proc = subprocess.Popen(
        [artifact_path, "--config", str(config_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Wait for "Listening on:" log line
    deadline = time.time() + 30
    listening = False
    while time.time() < deadline and proc.poll() is None:
        line = proc.stdout.readline()
        if line:
            logger.info("PicoLimbo: %s", line.rstrip())
            if "Listening on:" in line:
                listening = True
                break

    if not listening:
        proc.kill()
        proc.wait()
        raise RuntimeError("PicoLimbo did not start listening within 30 seconds")

    logger.info("Job %s: PicoLimbo is listening", job_id)
    return proc


def _test_step(job: dict, versions: list[str], server_proc: Optional[subprocess.Popen]) -> dict:
    """Run Minecraft tests for all versions.

    Skips versions already tested across all jobs with the same commit hash.
    For skipped versions, reuses screenshots from previous completed jobs.
    Returns updated test_results dict.
    """
    job_id = job["job_id"]
    commit_hash = job["commit_hash"]
    test_results = dict(job.get("test_results") or {})

    # Get all versions already tested for this commit hash (globally)
    globally_tested = database.get_tested_versions_for_commit(commit_hash)

    # Get the latest completed job's test results for screenshot lookups
    previous_results = database.get_latest_test_results_for_commit(commit_hash)

    # Ensure screenshots directory exists
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    # Clean old screenshots from game directory
    empty_directory(str(GAME_DIRECTORY / "screenshots"))

    virtual_device = VirtualInputController()

    try:
        for version in versions:
            if version in globally_tested:
                logger.info("Job %s: version %s already tested for commit %s, skipping", job_id, version, commit_hash[:8])
                # Look up screenshot from the previous completed job's test results
                screenshot_path = None
                if previous_results and version in previous_results:
                    screenshot_path = previous_results[version].get("screenshot_path")
                test_results[version] = {
                    "version": version,
                    "passed": True,
                    "screenshot_path": screenshot_path,
                    "duration_seconds": None,
                    "error": None,
                }
                # Persist after each version so we don't lose progress
                database.update_job(
                    job_id,
                    test_results=json.dumps(test_results),
                )
                continue

            logger.info("Job %s: testing version %s", job_id, version)
            result = test_single_version(version, commit_hash, virtual_device, SCREENSHOTS_DIR)
            test_results[version] = result

            # Persist after each version so we don't lose progress
            database.update_job(
                job_id,
                test_results=json.dumps(test_results),
            )
            # Update our local set so we don't re-test in this job either
            globally_tested.add(version)

    finally:
        virtual_device.close()

    return test_results


def _kill_server(server_proc: Optional[subprocess.Popen]) -> None:
    """Kill the PicoLimbo server process if running."""
    if server_proc and server_proc.poll() is None:
        logger.info("Killing PicoLimbo server")
        server_proc.kill()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Server did not terminate, forcing")
            server_proc.kill()


def run_job(job_id: str) -> None:
    """Run all steps for a job."""
    job = database.get_job_by_id(job_id)
    if not job:
        logger.error("Job %s not found", job_id)
        return

    versions = job.get("versions") or []
    if not versions:
        # Default to all versions if none specified
        from ..versions import ALL_VERSIONS
        versions = [str(v) for v in ALL_VERSIONS]
        database.update_job(job_id, versions=json.dumps(versions))

    server_proc = None

    try:
        # --- Build step ---
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

        # --- Server step ---
        # Re-fetch job in case artifact_path was just set
        job = database.get_job_by_id(job_id)
        server_proc = _server_step(job, versions)

        # --- Test step ---
        _update_job(job_id, current_step="testing")
        job = database.get_job_by_id(job_id)
        test_results = _test_step(job, versions, server_proc)

        # --- Done ---
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
        _kill_server(server_proc)
