"""Job orchestrator — uses domain services to execute the full job lifecycle."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .. import config
from .. import database
from ..application.build_service import BuildService
from ..application.server_context import ServerContext
from ..application.server_setup_service import ServerSetupService
from ..domain.job import Job
from ..infrastructure.artifact_repository import ArtifactRepository
from ..infrastructure.artifact_storage import ArtifactStorage
from ..infrastructure.cargo_build import CargoBuildAdapter
from ..infrastructure.config_writer import ConfigWriter
from ..infrastructure.git_repository import GitRepository
from ..minecraft.input import VirtualInputController
from ..minecraft.runner import test_single_version
from ..proxy.factory import ProxyFactory

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class JobOrchestrator:
    """Orchestrates the full job lifecycle: build → server setup → test → result persistence.

    Uses injected domain services and repositories. Tests can inject mocks.

    Parameters
    ----------
    builds_dir : Path
        Base directory where build artifacts are stored.
    proxy_factory : ProxyFactory
        Factory for creating proxy manager instances.
    config_writer : ConfigWriter
        Writer for configuration files.
    artifact_repo : ArtifactRepository
        Repository for downloading and caching Velocity artifacts.
    game_directory : Path
        Minecraft game directory.
    screenshots_dir : Path
        Directory where test screenshots are saved.
    """

    def __init__(
        self,
        builds_dir: Path,
        proxy_factory: ProxyFactory,
        config_writer: ConfigWriter,
        artifact_repo: ArtifactRepository,
        game_directory: Path,
        screenshots_dir: Path,
    ) -> None:
        self._builds_dir = builds_dir
        self._game_directory = game_directory
        self._screenshots_dir = screenshots_dir

        # Domain services
        self._server_setup = ServerSetupService(
            proxy_factory=proxy_factory,
            config_writer=config_writer,
            artifact_repo=artifact_repo,
        )

    def execute(self, job_id: str) -> None:
        """Execute the full job lifecycle.

        Parameters
        ----------
        job_id : str
            The job identifier.

        Returns
        -------
        None
        """
        # Fetch job
        job_dict = database.get_job_by_id(job_id)
        if not job_dict:
            logger.error("Job %s not found", job_id)
            return

        # Convert to domain object
        job = Job.from_dict(job_dict)

        # Resolve versions
        versions = job.versions
        if not versions:
            from ..versions import ALL_VERSIONS

            versions = [str(v) for v in ALL_VERSIONS]
            job = Job(
                job_id=job.job_id,
                repo_url=job.repo_url,
                ref=job.ref,
                owner=job.owner,
                versions=versions,
                proxy_type=job.proxy_type,
                forwarding_method=job.forwarding_method,
                plugins=job.plugins,
                login_wait_timeout=job.login_wait_timeout,
                mc_version=job.mc_version,
            )
            database.update_job(job_id, versions=json.dumps(versions))

        proxy_type = job.proxy_type.value if hasattr(job.proxy_type, "value") else job.proxy_type
        logger.info("Job %s: proxy_type=%r", job_id, proxy_type)

        server_context: Optional[ServerContext] = None
        try:
            # Build step
            self._update_status(job_id, "building", "building")
            self._run_build(job)
            self._update_status(job_id, "testing", "testing")

            # Re-fetch job to get artifact_path set by build
            job = Job.from_dict(database.get_job_by_id(job_id))

            # Server step
            server_context = self._run_server_setup(job, proxy_type)

            # Test step
            test_results = self._run_tests(job, versions)

            # Done
            self._update_status(
                job_id,
                "finished",
                "finished",
                test_results=json.dumps(test_results),
                eta_seconds=0,
            )
            logger.info("Job %s finished successfully", job_id)

        except Exception as e:
            logger.exception("Job %s failed", job_id)
            self._update_status(job_id, "failed", error_message=str(e))
        finally:
            # Cleanup is handled by ServerContext stop()
            if server_context is not None:
                server_context.stop()

    def _update_status(
        self,
        job_id: str,
        status: str,
        current_step: str = "",
        **extra_fields: object,
    ) -> None:
        """Update job status and compute ETA if testing."""
        fields: dict[str, object] = {"status": status}
        if current_step:
            fields["current_step"] = current_step
        fields.update(extra_fields)

        job = database.update_job(job_id, **fields)
        if job and status == "testing":
            eta = self._compute_eta(job)
            if eta is not None:
                database.update_job(job_id, eta_seconds=eta)

    def _compute_eta(self, job: dict) -> Optional[int]:
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

    def _run_build(self, job: Job) -> None:
        """Run the build step using BuildService."""
        git_repo = GitRepository(repos_dir=config.REPOS_DIR, timeout=1800.0)
        cargo = CargoBuildAdapter(timeout=1800.0, release=True)
        artifact_storage = ArtifactStorage(self._builds_dir)

        build_service = BuildService(git_repo, cargo, artifact_storage, self._builds_dir)
        result = build_service.build(
            job.repo_url.value, job.ref, job.owner, job.repo_url.value.split("/")[-1].replace(".git", "")
        )

        # Update job with artifact path
        database.update_job(job.job_id, artifact_path=str(result.artifact_path.value))
        logger.info("Job %s: build completed, artifact=%s", job.job_id, result.artifact_path.value)

    def _run_server_setup(
        self,
        job: Job,
        proxy_type: str,
    ) -> ServerContext:
        """Run the server setup step using ServerSetupService."""
        proxy_dir = Path(tempfile.mkdtemp(prefix="velocity_config_"))
        plugins_dir = config.PLUGINS_DIR
        webui_dir = Path("/tmp")

        return self._server_setup.setup(job, self._builds_dir, proxy_dir, plugins_dir, webui_dir)

    def _run_tests(
        self,
        job: Job,
        versions: list[str],
    ) -> dict:
        """Run tests for all versions."""
        job_id = job.job_id
        commit_hash = job.commit_hash.value
        test_results = dict(job.test_results or {})

        os.makedirs(self._screenshots_dir, exist_ok=True)

        from ..minecraft.env import empty_directory

        empty_directory(str(self._game_directory / "screenshots"))

        virtual_device = VirtualInputController()

        try:
            login_wait_timeout = job.login_wait_timeout
            for version in versions:
                current = database.get_job_by_id(job_id)
                if current and current.get("status") == "cancelled":
                    database.update_job(job_id, status="failed", error_message="Job was cancelled")
                    return test_results

                logger.info("Job %s: testing version %s", job_id, version)
                self._update_status(job_id, "testing", current_step=f"testing:{version}")

                result = test_single_version(
                    version, commit_hash, virtual_device, self._screenshots_dir, login_wait_timeout
                )
                test_results[version] = result

                # Persist after each version
                database.update_job(job_id, test_results=json.dumps(test_results))

        except Exception as e:
            self._update_status(job_id, "failed", error_message=str(e))
            raise
        finally:
            virtual_device.close()

        return test_results
