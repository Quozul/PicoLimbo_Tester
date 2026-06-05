"""Job runner — thin wrapper around JobOrchestrator.

Preserves the legacy run_job(job_id) and _compute_eta(job) module-level
functions for backward compatibility. All logic is delegated to
:class:`JobOrchestrator`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .. import config
from .. import database
from ..application.build_service import BuildService
from ..domain.job import Job
from ..infrastructure.artifact_repository import ArtifactRepository
from ..infrastructure.artifact_storage import ArtifactStorage
from ..infrastructure.cargo_build import CargoBuildAdapter
from ..infrastructure.config_writer import ConfigWriter
from ..infrastructure.git_repository import GitRepository
from ..proxy.factory import ProxyFactory
from .job_orchestrator import JobOrchestrator

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = config.SCREENSHOTS_DIR  # kept for backward compat


def _make_orchestrator() -> JobOrchestrator:
    """Create a JobOrchestrator with default dependencies."""
    git_repo = GitRepository(repos_dir=config.REPOS_DIR, timeout=1800.0)
    cargo = CargoBuildAdapter(timeout=1800.0, release=True)
    artifact_storage = ArtifactStorage(config.BUILDS_DIR)
    build_service = BuildService(git_repo, cargo, artifact_storage, config.BUILDS_DIR)

    return JobOrchestrator(
        builds_dir=config.BUILDS_DIR,
        proxy_factory=ProxyFactory(
            ConfigWriter(),
            forwarding_secret=config._FORWARDING_SECRET,
        ),
        config_writer=ConfigWriter(),
        artifact_repo=ArtifactRepository(
            api_base=config.VELOCITY_API_BASE,
            cache_dir=config.PROXY_CACHE_DIR / "velocity",
        ),
        game_directory=config.GAME_DIRECTORY,
        screenshots_dir=config.SCREENSHOTS_DIR,
        build_service=build_service,
    )


def run_job(job_id: str) -> None:
    """Run all steps for a job.

    Thin wrapper that creates a :class:`JobOrchestrator` and delegates to it.
    """
    _make_orchestrator().execute(job_id)


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
    return _make_orchestrator()._compute_eta(job)
