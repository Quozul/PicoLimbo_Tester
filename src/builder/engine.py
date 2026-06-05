"""PicoLimbo build engine with idempotent caching."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional


from .. import config
from .. import database
from ..application.build_service import BuildResult
from ..di import get_build_service, get_git_repo

logger = logging.getLogger(__name__)

# GitHub URL pattern: https://github.com/{owner}/{repo} (with or without .git)
GITHUB_URL_RE = re.compile(
    r"^https://github\.com/([^/]+)/([^/]+)(?:\.git)?$"
)

# Git commit hash: 40-character hex string
COMMIT_HASH_RE = re.compile(r"^[0-9a-fA-F]{40}$")


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
    owner = match.group(1)
    repo_name = match.group(2)
    # Strip .git suffix if present (regex captures it as part of group 2)
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    return owner, repo_name


def is_commit_hash(ref: str) -> bool:
    """Check if ref looks like a git commit hash (40-char hex)."""
    return bool(COMMIT_HASH_RE.match(ref))


def _get_build_service() -> BuildService:
    """Return the shared BuildService from DI."""
    return get_build_service()


def build_project(repo_url: str, ref: str, owner: str, repo_name: str) -> BuildResult:
    """Build a project. Returns BuildResult with commit_hash and artifact_path."""
    return _get_build_service().build(repo_url, ref, owner, repo_name)


def create_job(
    repo_url: str,
    ref: str,
    versions: Optional[list[str]] = None,
    proxy: str = "none",
    forwarding_method: str = "modern",
    plugin: Optional[str] = None,
    plugins: Optional[list[str]] = None,
    login_wait_timeout: int = 30,
) -> dict:
    """Always create a new job.

    Step-level logic handles skipping/reusing where appropriate:
    - Repo: updates existing clone instead of re-cloning
    - Build: reuses artifact if already built for this commit hash
    - Tests: skips versions already tested for this commit hash

    Resolves the commit hash immediately, so the returned job has
    commit_hash set but artifact_path is null until build finishes.
    """
    owner, repo_name = extract_owner_from_url(repo_url)

    # Ensure repo is cloned (or already exists)
    repo_path = get_git_repo().clone(owner, repo_name)

    # Resolve commit hash
    commit_hash = get_git_repo().resolve(repo_path, ref)

    # Always create a new job - step-level logic handles skipping
    job = database.create_job(
        repo_url, ref, owner, commit_hash, versions or [],
        proxy, forwarding_method, plugin, plugins, login_wait_timeout,
    )
    logger.info("Created new job %s for %s@%s", job["job_id"], repo_url, ref)
    return job


def get_artifact_file(job_id: str) -> Path | None:
    """Get the artifact file path for a job. Returns None if not built."""
    job = database.get_job_by_id(job_id)
    if not job or not job.get("artifact_path"):
        return None
    return Path(job["artifact_path"])
