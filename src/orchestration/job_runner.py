"""Job orchestrator: build → server → tests."""

import json
import logging
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .. import database
from .. import models
from ..builder import engine
from ..minecraft.env import create_servers_dat
from ..minecraft.input import VirtualInputController
from ..minecraft.runner import test_single_version, empty_directory
from ..proxy import get_proxy_manager

logger = logging.getLogger(__name__)

# Estimated seconds per Minecraft version test (for ETA calculation)
SECONDS_PER_VERSION = 90

# PicoLimbo config for direct (no-proxy) mode
SERVER_CONFIG_CONTENT = 'bind = "0.0.0.0:25565"\n'

# servers.dat address (must match server bind)
SERVER_ADDRESS = "127.0.0.1:25565"

# Internal port PicoLimbo binds to when a proxy is in front of it
PICO_LIMBO_INTERNAL_PORT = 30066

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


# Map Velocity forwarding methods to PicoLimbo forwarding methods
_VELOCITY_TO_PICOLIMBO_METHOD = {
    "none": "NONE",
    "legacy": "LEGACY",
    "bungeeguard": "BUNGEE_GUARD",
    "modern": "MODERN",
}


def _generate_pico_limbo_config(proxy_type: str, forwarding_method: str = "modern", forwarding_secret: str = "sup3r-s3cr3t") -> str:
    """Generate PicoLimbo server.toml content.

    For proxy mode, includes the [forwarding] section with the appropriate method.
    """
    if proxy_type and proxy_type != "none":
        lines = [f'bind = "127.0.0.1:{PICO_LIMBO_INTERNAL_PORT}"']
        method = _VELOCITY_TO_PICOLIMBO_METHOD.get(forwarding_method, "MODERN")
        lines.append(f'\n[forwarding]')
        lines.append(f'method = "{method}"')
        if forwarding_method == "bungeeguard":
            lines.append(f'tokens = ["{forwarding_secret}"]')
        else:
            lines.append(f'secret = "{forwarding_secret}"')
        return "\n".join(lines)
    else:
        return SERVER_CONFIG_CONTENT


def _server_step(
    job: dict, versions: list[str], proxy_type: str = "none"
) -> tuple[Optional[subprocess.Popen], Optional[subprocess.Popen]]:
    """Start proxy (if any) and PicoLimbo server, then wait for them to be ready.

    Returns:
        A tuple of (proxy_process, pico_limbo_process).
        proxy_process is the proxy (e.g. Velocity), or None for no-proxy mode.
        pico_limbo_process is the PicoLimbo process.
    """
    job_id = job["job_id"]
    artifact_path = job.get("artifact_path")
    if not artifact_path:
        raise RuntimeError("No artifact path for job")

    proxy_proc: Optional[subprocess.Popen] = None
    pico_limbo_proc: Optional[subprocess.Popen] = None

    # Extract forwarding config from job
    forwarding_method = job.get("forwarding_method", "modern")
    forwarding_secret = job.get("forwarding_secret", "sup3r-s3cr3t")

    # --- Proxy mode ---
    if proxy_type and proxy_type != "none":
        proxy_manager = get_proxy_manager(proxy_type)
        if proxy_manager is None:
            raise ValueError(f"Unknown or unsupported proxy type: {proxy_type}")

        # Use a temp directory for the proxy config
        proxy_config_dir = Path(tempfile.mkdtemp(prefix="velocity_config_"))

        # Start proxy first
        logger.info("Job %s: starting proxy (%s)", job_id, proxy_type)
        proxy_proc = proxy_manager.start(
            proxy_config_dir,
            PICO_LIMBO_INTERNAL_PORT,
            forwarding_method=forwarding_method,
            forwarding_secret=forwarding_secret,
        )
        proxy_manager.wait_for_ready(proxy_proc)
        logger.info("Job %s: proxy is ready", job_id)

    # Write servers.dat (always points to the proxy port)
    servers_dat = GAME_DIRECTORY / "servers.dat"
    create_servers_dat(str(servers_dat), SERVER_ADDRESS)

    # Write PicoLimbo config with forwarding section if using a proxy
    config_path = Path("/tmp/server.toml")
    config_path.write_text(_generate_pico_limbo_config(proxy_type, forwarding_method, forwarding_secret))

    # Start PicoLimbo
    logger.info("Job %s: starting PicoLimbo server", job_id)
    pico_limbo_proc = subprocess.Popen(
        [artifact_path, "--config", str(config_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Wait for "Listening on:" log line
    deadline = time.time() + 30
    listening = False
    while time.time() < deadline and pico_limbo_proc.poll() is None:
        line = pico_limbo_proc.stdout.readline()
        if line:
            logger.info("PicoLimbo: %s", line.rstrip())
            if "Listening on:" in line:
                listening = True
                break

    if not listening:
        pico_limbo_proc.kill()
        pico_limbo_proc.wait()
        raise RuntimeError("PicoLimbo did not start listening within 30 seconds")

    logger.info("Job %s: PicoLimbo is listening", job_id)

    return proxy_proc, pico_limbo_proc


def _test_step(job: dict, versions: list[str], server_proc: Optional[subprocess.Popen]) -> dict:
    """Run Minecraft tests for all versions.

    Always re-runs tests for every version — a previously captured screenshot
    does not guarantee the test truly passed, so we never skip a version.

    Returns updated test_results dict.
    """
    job_id = job["job_id"]
    commit_hash = job["commit_hash"]
    test_results = dict(job.get("test_results") or {})

    # Ensure screenshots directory exists
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    # Clean old screenshots from game directory
    empty_directory(str(GAME_DIRECTORY / "screenshots"))

    virtual_device = VirtualInputController()

    try:
        for version in versions:
            logger.info("Job %s: testing version %s", job_id, version)
            result = test_single_version(version, commit_hash, virtual_device, SCREENSHOTS_DIR)
            test_results[version] = result

            # Persist after each version so we don't lose progress
            database.update_job(
                job_id,
                test_results=json.dumps(test_results),
            )

    finally:
        virtual_device.close()

    return test_results


def _kill_server(
    proxy_proc: Optional[subprocess.Popen], pico_limbo_proc: Optional[subprocess.Popen]
) -> None:
    """Kill the PicoLimbo server and proxy processes if running.

    Kills PicoLimbo first, then the proxy, in reverse order of startup.
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

    proxy_type = job.get("proxy", "none") or "none"
    logger.info("Job %s: proxy_type=%r", job_id, proxy_type)

    proxy_proc: Optional[subprocess.Popen] = None
    pico_limbo_proc: Optional[subprocess.Popen] = None

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
        proxy_proc, pico_limbo_proc = _server_step(job, versions, proxy_type)

        # --- Test step ---
        _update_job(job_id, current_step="testing")
        job = database.get_job_by_id(job_id)
        test_results = _test_step(job, versions, pico_limbo_proc)

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
        _kill_server(proxy_proc, pico_limbo_proc)
