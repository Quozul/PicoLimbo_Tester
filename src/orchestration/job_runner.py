"""Job runner — thin wrapper around JobOrchestrator.

Preserves the legacy run_job(job_id) and _compute_eta(job) module-level
functions for backward compatibility. All logic is delegated to
:class:`JobOrchestrator`.
"""

from __future__ import annotations

import logging
from typing import Optional

from .. import config
from ..di import (
    get_artifact_repo,
    get_build_service,
    get_config_writer,
    get_proxy_factory,
)
from .job_orchestrator import JobOrchestrator

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = config.SCREENSHOTS_DIR  # kept for backward compat


def _make_orchestrator() -> JobOrchestrator:
    """Create a JobOrchestrator with shared dependencies from DI."""
    return JobOrchestrator(
        builds_dir=config.BUILDS_DIR,
        proxy_factory=get_proxy_factory(),
        config_writer=get_config_writer(),
        artifact_repo=get_artifact_repo(),
        game_directory=config.GAME_DIRECTORY,
        screenshots_dir=config.SCREENSHOTS_DIR,
        build_service=get_build_service(),
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
