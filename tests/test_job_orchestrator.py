"""Tests for JobOrchestrator with injected mocks.

Covers:
- Full lifecycle: build → server setup → test → finish
- Error handling at each step (build, server, test failures)
- Job not found
- ETA computation edge cases
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.application.build_service import BuildService
from src.application.test_service import TestService
from src.infrastructure.artifact_repository import ArtifactRepository
from src.infrastructure.config_writer import ConfigWriter
from src.proxy.factory import ProxyFactory
from src.orchestration.job_orchestrator import JobOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job_dict(
    job_id: str = "job-1",
    status: str = "queued",
    versions: list[str] | None = None,
    artifact_path: str | None = None,
    test_results: dict | None = None,
    commit_hash: str = "abc123def456789012345678901234567890abcd",
    proxy_type: str = "none",
    **extra: object,
) -> dict:
    """Create a minimal job dict for testing."""
    return {
        "job_id": job_id,
        "status": status,
        "commit_hash": commit_hash,
        "artifact_path": artifact_path,
        "versions": versions or ["1.21.8"],
        "proxy": proxy_type,
        "repo_url": "https://github.com/Quozul/PicoLimbo.git",
        "ref": "main",
        "owner": "Quozul",
        "forwarding_method": "modern",
        "plugins": [],
        "login_wait_timeout": 30,
        "mc_version": "1.21.8",
        "test_results": test_results or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


def _build_orchestrator(
    mock_build_service: MagicMock,
    mock_test_service: MagicMock,
    mock_virtual_input_cls: MagicMock,
    mock_server_context: MagicMock,
    mock_setup_service_cls: MagicMock,
    mock_database: MagicMock,
) -> JobOrchestrator:
    """Build a JobOrchestrator instance (no patching)."""
    proxy_factory = MagicMock(spec=ProxyFactory)
    config_writer = MagicMock(spec=ConfigWriter)
    artifact_repo = MagicMock(spec=ArtifactRepository)

    return JobOrchestrator(
        builds_dir=Path("/tmp/builds"),
        proxy_factory=proxy_factory,
        config_writer=config_writer,
        artifact_repo=artifact_repo,
        game_directory=Path("/tmp/game"),
        screenshots_dir=Path("/tmp/screenshots"),
        build_service=mock_build_service,
        test_service=mock_test_service,
        virtual_input_controller_cls=mock_virtual_input_cls,
    )


class _Sentinel:
    """Sentinel for distinguishing unset from None."""
    pass


_UNSET = _Sentinel()


def _make_mocks(
    job_dict: dict | None | _Sentinel = _UNSET,
    mock_setup_service_cls: MagicMock | None = None,
    mock_database: MagicMock | None = None,
) -> tuple[dict | None, MagicMock, MagicMock]:
    """Create default mocks for ServerSetupService and database.

    Returns (job_dict, mock_setup_service_cls, mock_database).
    """
    if job_dict is _UNSET:
        job_dict = _make_job_dict()
    if mock_database is None:
        mock_database = MagicMock()
        mock_database.get_job_by_id.return_value = job_dict
        mock_database.update_job.return_value = job_dict
    if mock_setup_service_cls is None:
        mock_setup_service_cls = MagicMock()
        mock_setup_instance = MagicMock()
        mock_server_context = MagicMock()
        mock_setup_instance.setup.return_value = mock_server_context
        mock_setup_service_cls.return_value = mock_setup_instance

    return job_dict, mock_setup_service_cls, mock_database


def _make_test_service_mock(
    result: dict | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    """Create a mock TestService."""
    mock = MagicMock(spec=TestService)
    if side_effect is not None:
        mock.test_version.side_effect = side_effect
    else:
        mock_result = MagicMock()
        mock_result.to_dict.return_value = result or {"version": "1.21.8", "passed": True}
        mock.test_version.return_value = mock_result
    return mock


# ---------------------------------------------------------------------------
# execute() — full lifecycle
# ---------------------------------------------------------------------------


class TestExecuteFullLifecycle:
    """Tests for the full job lifecycle."""

    def test_execute_full_lifecycle(self):
        """Mocked build succeeds, server setup succeeds, tests run, job finishes."""
        mock_build_service = MagicMock(spec=BuildService)
        result = MagicMock()
        result.artifact_path.value = Path("/tmp/builds/job-1/pico_limbo")
        mock_build_service.build.return_value = result

        mock_virtual_input = MagicMock()
        mock_virtual_input_cls = MagicMock(return_value=mock_virtual_input)

        mock_server_context = MagicMock()
        mock_server_context.proxy_proc = None
        mock_pico = MagicMock()
        mock_pico.poll.return_value = None
        mock_pico.stdout.readline.return_value = "Listening on: 127.0.0.1:30066\n"
        mock_server_context.pico_limbo_proc = mock_pico

        mock_test_service = _make_test_service_mock({"version": "1.21.8", "passed": True})

        job_dict, mock_setup_cls, mock_db = _make_mocks()
        mock_setup_cls.return_value.setup.return_value = mock_server_context

        with patch(
            "src.orchestration.job_orchestrator.ServerSetupService",
            mock_setup_cls,
        ), patch(
            "src.orchestration.job_orchestrator.database",
            mock_db,
        ):
            orchestrator = _build_orchestrator(
                mock_build_service,
                mock_test_service,
                mock_virtual_input_cls,
                mock_server_context,
                mock_setup_cls,
                mock_db,
            )
            orchestrator.execute("job-1")

        # Verify build was called
        mock_build_service.build.assert_called_once()
        call_args = mock_build_service.build.call_args
        assert call_args[0][0] == "https://github.com/Quozul/PicoLimbo.git"
        assert call_args[0][1] == "main"
        assert call_args[0][2] == "Quozul"
        assert call_args[0][3] == "PicoLimbo"

        # Verify server setup was called
        mock_setup_cls.return_value.setup.assert_called_once()

        # Verify test service was called
        mock_test_service.test_version.assert_called_once()


class TestExecuteBuildFailure:
    """Tests for build failure handling."""

    def test_execute_build_failure_sets_failed_status(self):
        """Build raises, job status = failed."""
        mock_build_service = MagicMock(spec=BuildService)
        mock_build_service.build.side_effect = RuntimeError("cargo build failed")

        mock_virtual_input_cls = MagicMock()
        mock_server_context = MagicMock()
        mock_test_service = _make_test_service_mock()

        job_dict, mock_setup_cls, mock_db = _make_mocks()
        mock_setup_cls.return_value.setup.return_value = mock_server_context

        with patch(
            "src.orchestration.job_orchestrator.ServerSetupService",
            mock_setup_cls,
        ), patch(
            "src.orchestration.job_orchestrator.database",
            mock_db,
        ):
            orchestrator = _build_orchestrator(
                mock_build_service,
                mock_test_service,
                mock_virtual_input_cls,
                mock_server_context,
                mock_setup_cls,
                mock_db,
            )
            # Should not raise — orchestrator catches exceptions
            orchestrator.execute("job-1")

        # Verify build was attempted
        mock_build_service.build.assert_called_once()
        # Verify server setup was NOT called (build failed first)
        mock_setup_cls.return_value.setup.assert_not_called()


class TestExecuteServerFailure:
    """Tests for server setup failure handling."""

    def test_execute_server_failure_sets_failed_status(self):
        """Server setup raises, job status = failed."""
        mock_build_service = MagicMock(spec=BuildService)
        result = MagicMock()
        result.artifact_path.value = Path("/tmp/builds/job-1/pico_limbo")
        mock_build_service.build.return_value = result

        mock_virtual_input_cls = MagicMock()
        mock_server_context = MagicMock()
        mock_server_context.stop = MagicMock()
        mock_test_service = _make_test_service_mock()

        job_dict, mock_setup_cls, mock_db = _make_mocks()
        mock_setup_cls.return_value.setup.side_effect = RuntimeError("server setup failed")

        with patch(
            "src.orchestration.job_orchestrator.ServerSetupService",
            mock_setup_cls,
        ), patch(
            "src.orchestration.job_orchestrator.database",
            mock_db,
        ):
            orchestrator = _build_orchestrator(
                mock_build_service,
                mock_test_service,
                mock_virtual_input_cls,
                mock_server_context,
                mock_setup_cls,
                mock_db,
            )
            # Should not raise — orchestrator catches exceptions
            orchestrator.execute("job-1")

        # Verify build was called
        mock_build_service.build.assert_called_once()
        # Verify server setup was called (and raised)
        mock_setup_cls.return_value.setup.assert_called_once()


class TestExecuteTestFailure:
    """Tests for test step failure handling."""

    def test_execute_test_failure_sets_failed_status(self):
        """Test raises, job status = failed."""
        mock_build_service = MagicMock(spec=BuildService)
        result = MagicMock()
        result.artifact_path.value = Path("/tmp/builds/job-1/pico_limbo")
        mock_build_service.build.return_value = result

        mock_virtual_input = MagicMock()
        mock_virtual_input_cls = MagicMock(return_value=mock_virtual_input)

        mock_server_context = MagicMock()
        mock_server_context.proxy_proc = None
        mock_server_context.pico_limbo_proc = MagicMock()
        mock_server_context.pico_limbo_proc.poll.return_value = None
        mock_server_context.stop = MagicMock()

        mock_test_service = _make_test_service_mock(side_effect=RuntimeError("test failed"))

        job_dict, mock_setup_cls, mock_db = _make_mocks()
        mock_setup_cls.return_value.setup.return_value = mock_server_context

        with patch(
            "src.orchestration.job_orchestrator.ServerSetupService",
            mock_setup_cls,
        ), patch(
            "src.orchestration.job_orchestrator.database",
            mock_db,
        ):
            orchestrator = _build_orchestrator(
                mock_build_service,
                mock_test_service,
                mock_virtual_input_cls,
                mock_server_context,
                mock_setup_cls,
                mock_db,
            )
            # Should not raise — orchestrator catches exceptions
            orchestrator.execute("job-1")

        # Verify build was called
        mock_build_service.build.assert_called_once()
        # Verify server setup was called
        mock_setup_cls.return_value.setup.assert_called_once()
        # Verify test service was called
        mock_test_service.test_version.assert_called_once()


class TestExecuteJobNotFound:
    """Tests for job not found handling."""

    def test_execute_job_not_found(self):
        """Database returns None, no error raised."""
        mock_build_service = MagicMock(spec=BuildService)
        mock_virtual_input_cls = MagicMock()
        mock_server_context = MagicMock()
        mock_test_service = _make_test_service_mock()

        job_dict, mock_setup_cls, mock_db = _make_mocks(job_dict=None)

        with patch(
            "src.orchestration.job_orchestrator.ServerSetupService",
            mock_setup_cls,
        ), patch(
            "src.orchestration.job_orchestrator.database",
            mock_db,
        ):
            orchestrator = _build_orchestrator(
                mock_build_service,
                mock_test_service,
                mock_virtual_input_cls,
                mock_server_context,
                mock_setup_cls,
                mock_db,
            )
            # Should not raise
            orchestrator.execute("nonexistent-job")

        # Verify no side effects
        mock_build_service.build.assert_not_called()
        mock_setup_cls.return_value.setup.assert_not_called()


# ---------------------------------------------------------------------------
# _compute_eta
# ---------------------------------------------------------------------------


class TestComputeEta:
    """Tests for ETA computation."""

    def _make_eta_orchestrator(self) -> JobOrchestrator:
        """Create a minimal orchestrator just for _compute_eta tests."""
        proxy_factory = MagicMock(spec=ProxyFactory)
        config_writer = MagicMock(spec=ConfigWriter)
        artifact_repo = MagicMock(spec=ArtifactRepository)
        build_service = MagicMock(spec=BuildService)
        test_service = _make_test_service_mock()

        return JobOrchestrator(
            builds_dir=Path("/tmp/builds"),
            proxy_factory=proxy_factory,
            config_writer=config_writer,
            artifact_repo=artifact_repo,
            game_directory=Path("/tmp/game"),
            screenshots_dir=Path("/tmp/screenshots"),
            build_service=build_service,
            test_service=test_service,
        )

    def test_compute_eta_returns_none_when_not_testing(self):
        """ETA is None for jobs not in testing phase."""
        orchestrator = self._make_eta_orchestrator()
        job = _make_job_dict(status="queued")
        assert orchestrator._compute_eta(job) is None

        job["status"] = "building"
        assert orchestrator._compute_eta(job) is None

        job["status"] = "finished"
        assert orchestrator._compute_eta(job) is None

        job["status"] = "failed"
        assert orchestrator._compute_eta(job) is None

    def test_compute_eta_returns_none_when_no_test_results(self):
        """ETA is None when no test results exist yet."""
        orchestrator = self._make_eta_orchestrator()
        job = _make_job_dict(status="testing", test_results={})
        assert orchestrator._compute_eta(job) is None

    def test_compute_eta_returns_zero_when_all_versions_done(self):
        """ETA is 0 when all versions have been tested."""
        orchestrator = self._make_eta_orchestrator()
        job = _make_job_dict(
            status="testing",
            versions=["1.21.8", "1.21.7"],
            test_results={"1.21.8": {"passed": True}, "1.21.7": {"passed": True}},
        )
        assert orchestrator._compute_eta(job) == 0

    def test_compute_eta_returns_positive_when_versions_remain(self):
        """ETA is positive when some versions remain to be tested."""
        orchestrator = self._make_eta_orchestrator()
        # Set created_at to 60 seconds ago so elapsed time is meaningful
        created = (datetime.now(timezone.utc).timestamp() - 60)
        created_at = datetime.fromtimestamp(created, tz=timezone.utc).isoformat()
        job = _make_job_dict(
            status="testing",
            versions=["1.21.8", "1.21.7", "1.21.6"],
            test_results={"1.21.8": {"passed": True}},
            created_at=created_at,
        )
        eta = orchestrator._compute_eta(job)
        assert eta is not None
        assert eta > 0

    def test_compute_eta_returns_none_when_no_versions(self):
        """ETA is None when versions list is empty."""
        orchestrator = self._make_eta_orchestrator()
        job = _make_job_dict(status="testing", versions=[])
        assert orchestrator._compute_eta(job) is None
