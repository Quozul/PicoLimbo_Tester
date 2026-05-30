"""PicoLimbo build engine with idempotent caching and a single-worker queue."""

import logging
import re
import subprocess
import threading
from pathlib import Path
from typing import Optional

import database

logger = logging.getLogger(__name__)

REPOS_DIR = Path("/app/repos")
BUILDS_DIR = Path("/app/builds")

# GitHub URL pattern: https://github.com/{owner}/{repo}.git
GITHUB_URL_RE = re.compile(
    r"^https://github\.com/([^/]+)/([^/]+)\.git$"
)

# Git commit hash: 40-character hex string
COMMIT_HASH_RE = re.compile(r"^[0-9a-f]{40}$")

# Lock to ensure only one build runs at a time
_build_lock = threading.Lock()


def extract_owner_from_url(repo_url: str) -> tuple[str, str]:
    """Extract (owner, repo_name) from a GitHub URL.

    Raises ValueError if the URL is not a valid GitHub repository URL.
    """
    match = GITHUB_URL_RE.match(repo_url)
    if not match:
        raise ValueError(
            f"Only GitHub repository URLs are allowed. "
            f"Got: {repo_url}"
        )
    return match.group(1), match.group(2)


def is_commit_hash(ref: str) -> bool:
    """Check if ref looks like a git commit hash (40-char hex)."""
    return bool(COMMIT_HASH_RE.match(ref))


def _run(cmd: list[str], cwd: Path) -> str:
    """Run a command and return stdout."""
    logger.info("Running: %s (cwd=%s)", " ".join(cmd), cwd)
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=1800,  # 30 minutes max
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def ensure_repo_cloned(owner: str, repo_name: str) -> Path:
    """Clone the repo if it doesn't exist, otherwise return existing path."""
    repo_path = REPOS_DIR / owner / repo_name
    if repo_path.exists() and (repo_path / ".git").exists():
        logger.info("Repo already cloned at %s", repo_path)
    else:
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        _run(
            ["git", "clone", "--depth", "1",
             f"https://github.com/{owner}/{repo_name}.git",
             str(repo_path)],
            cwd=Path.home(),
        )
        logger.info("Cloned repo to %s", repo_path)
    return repo_path


def resolve_commit(repo_path: Path, ref: str) -> str:
    """Resolve a ref (branch name or commit hash) to a commit hash.

    If ref is a branch, fetches latest and checks it out.
    If ref is a commit hash, checks it out directly.
    """
    if is_commit_hash(ref):
        commit_hash = ref
        _run(["git", "checkout", ref], cwd=repo_path)
        logger.info("Checked out commit %s", commit_hash)
    else:
        # Fetch latest for the branch
        _run(["git", "fetch", "origin", ref], cwd=repo_path)
        _run(["git", "checkout", ref], cwd=repo_path)
        # Resolve to full commit hash
        output = _run(["git", "rev-parse", "HEAD"], cwd=repo_path)
        commit_hash = output
        logger.info("Branch '%s' resolved to commit %s", ref, commit_hash)
    return commit_hash


def build_project(repo_path: Path, commit_hash: str, owner: str, ref: str) -> str:
    """Build PicoLimbo with cargo. Returns the artifact path."""
    artifact_dir = BUILDS_DIR / owner / ref / commit_hash
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "pico_limbo"

    if artifact_path.exists():
        logger.info("Artifact already exists at %s", artifact_path)
        return str(artifact_path)

    _run(["cargo", "build", "--release"], cwd=repo_path)

    # Copy artifact to our builds directory for persistence
    source = repo_path / "target" / "release" / "pico_limbo"
    if not source.exists():
        raise FileNotFoundError(
            f"Build artifact not found at {source}. "
            f"Cargo build may have failed silently."
        )
    import shutil
    shutil.copy2(str(source), str(artifact_path))
    logger.info("Artifact built and copied to %s", artifact_path)
    return str(artifact_path)


def create_or_get_job(repo_url: str, ref: str) -> dict:
    """Create a new job or return existing one (idempotent).

    Resolves the commit hash immediately, so the returned job has
    commit_hash set but artifact_path is null until build finishes.
    """
    owner, repo_name = extract_owner_from_url(repo_url)

    # Ensure repo is cloned (or already exists)
    repo_path = ensure_repo_cloned(owner, repo_name)

    # Resolve commit hash
    commit_hash = resolve_commit(repo_path, ref)

    # Idempotency check: if a job for this (repo_url, commit_hash) exists, return it
    existing = database.get_job_by_key(repo_url, commit_hash)
    if existing:
        logger.info("Existing job found for %s@%s: %s", repo_url, commit_hash, existing["job_id"])
        return existing

    # Create new job
    job = database.create_job(repo_url, ref, owner, commit_hash)
    logger.info("Created new job %s for %s@%s", job["job_id"], repo_url, ref)
    return job


def get_job_status(job_id: str) -> Optional[dict]:
    """Get job status. Returns None if not found."""
    return database.get_job_by_id(job_id)


def get_artifact_path(job: dict) -> Optional[str]:
    """Get the artifact path from a job dict."""
    return job.get("artifact_path")


def get_artifact_file(job_id: str) -> Optional[Path]:
    """Get the artifact file path for a job. Returns None if not built."""
    job = database.get_job_by_id(job_id)
    if not job or not job.get("artifact_path"):
        return None
    return Path(job["artifact_path"])


def _process_queue() -> None:
    """Background worker: process queued jobs one at a time."""
    logger.info("Build queue worker started")
    while True:
        # Get next queued job
        jobs = database.get_queued_jobs(limit=1)
        if not jobs:
            # No queued jobs, wait a bit
            threading.Event().wait(2)
            continue

        job = jobs[0]
        job_id = job["job_id"]

        # Acquire lock (ensures single build at a time)
        with _build_lock:
            # Re-read job to check it's still queued (might have been taken)
            current = database.get_job_by_id(job_id)
            if not current or current["status"] != "queued":
                continue

            logger.info("Processing job %s", job_id)
            database.update_job(job_id, status="building")

            try:
                owner = current["owner"]
                repo_name = current["repo_url"].split("/")[-1].replace(".git", "")
                ref = current["ref"]
                commit_hash = current["commit_hash"]

                repo_path = ensure_repo_cloned(owner, repo_name)
                # Re-resolve commit in case it changed (branch moved)
                commit_hash = resolve_commit(repo_path, ref)
                # Update job with latest commit hash
                database.update_job(job_id, commit_hash=commit_hash)

                artifact_path = build_project(repo_path, commit_hash, owner, ref)
                database.update_job(job_id, status="finished", artifact_path=artifact_path)
                logger.info("Job %s finished: %s", job_id, artifact_path)

            except Exception as e:
                logger.exception("Job %s failed: %s", job_id, e)
                database.update_job(job_id, status="failed")


def recover_stuck_jobs() -> None:
    """On startup, recover jobs stuck in 'building' state."""
    building = database.get_building_jobs()
    for job in building:
        artifact_path = job.get("artifact_path")
        if artifact_path and Path(artifact_path).exists():
            logger.info("Recovering job %s: artifact exists, marking finished", job["job_id"])
            database.update_job(job["job_id"], status="finished")
        else:
            logger.info("Recovering job %s: re-queuing", job["job_id"])
            database.update_job(job["job_id"], status="queued")


def start_queue_worker() -> threading.Thread:
    """Start the background queue worker thread. Returns the thread."""
    recover_stuck_jobs()
    t = threading.Thread(target=_process_queue, daemon=True, name="build-worker")
    t.start()
    return t
