"""PicoLimbo build engine with idempotent caching."""

import logging
import re
import shutil
from pathlib import Path
from typing import Optional

from .. import config
from .. import database
from ..infrastructure import cargo_build as cargo_build_module
from ..infrastructure import git_repository as git_repo_module

logger = logging.getLogger(__name__)

BUILDS_DIR = config.BUILDS_DIR

# GitHub URL pattern: https://github.com/{owner}/{repo} (with or without .git)
GITHUB_URL_RE = re.compile(
    r"^https://github\.com/([^/]+)/([^/]+)(?:\.git)?$"
)

# Git commit hash: 40-character hex string
COMMIT_HASH_RE = re.compile(r"^[0-9a-fA-F]{40}$")

# Module-level adapters (lazy-initialised on first use)
_git_repo: git_repo_module.GitRepository | None = None
_cargo: cargo_build_module.CargoBuildAdapter | None = None


def _get_git_repo() -> git_repo_module.GitRepository:
    """Return the module-level GitRepository, creating it lazily."""
    global _git_repo
    if _git_repo is None:
        _git_repo = git_repo_module.GitRepository(repos_dir=config.REPOS_DIR)
    return _git_repo


def _get_cargo() -> cargo_build_module.CargoBuildAdapter:
    """Return the module-level CargoBuildAdapter, creating it lazily."""
    global _cargo
    if _cargo is None:
        _cargo = cargo_build_module.CargoBuildAdapter(
            timeout=config.GIT_CARGO_TIMEOUT,
        )
    return _cargo


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


def build_project(repo_path: Path, commit_hash: str, owner: str, ref: str) -> str:
    """Build PicoLimbo with cargo. Returns the artifact path."""
    artifact_dir = BUILDS_DIR / owner / ref / commit_hash
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "pico_limbo"

    if artifact_path.exists():
        logger.info("Artifact already exists at %s", artifact_path)
        return str(artifact_path)

    source = _get_cargo().build(repo_path)

    # Copy artifact to our builds directory for persistence
    if not source.exists():
        raise FileNotFoundError(
            f"Build artifact not found at {source}. "
            f"Cargo build may have failed silently."
        )
    shutil.copy2(str(source), str(artifact_path))
    logger.info("Artifact built and copied to %s", artifact_path)
    return str(artifact_path)


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
    repo_path = _get_git_repo().clone(owner, repo_name)

    # Resolve commit hash
    commit_hash = _get_git_repo().resolve(repo_path, ref)

    # Always create a new job - step-level logic handles skipping
    job = database.create_job(
        repo_url, ref, owner, commit_hash, versions or [],
        proxy, forwarding_method, plugin, plugins, login_wait_timeout,
    )
    logger.info("Created new job %s for %s@%s", job["job_id"], repo_url, ref)
    return job


def get_artifact_file(job_id: str) -> Optional[Path]:
    """Get the artifact file path for a job. Returns None if not built."""
    job = database.get_job_by_id(job_id)
    if not job or not job.get("artifact_path"):
        return None
    return Path(job["artifact_path"])
