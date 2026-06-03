"""Tests for ServerSetupService and ServerContext.

Covers:
- ServerSetupService setup (happy path, artifact missing, no proxy)
- ServerContext lifecycle (stop, cleanup)
- Integration with mocked dependencies
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.application.server_context import ServerContext
from src.application.server_setup_service import ServerSetupService
from src.domain.job import Job
from src.domain.value_objects import (
    ArtifactPath,
    CommitHash,
    ForwardingMethod,
    JobId,
    JobStatus,
    ProxyType,
    RepoUrl,
    Version,
)
from src.infrastructure.artifact_repository import ArtifactRepository
from src.infrastructure.config_writer import ConfigWriter


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_job() -> Job:
    """Create a mock Job for testing."""
    return Job(
        job_id=JobId("test-job-1"),
        repo_url=RepoUrl("https://github.com/test-owner/test-repo.git"),
        ref="abc123def456",
        commit_hash=CommitHash("abc123def456789012345678901234567890abcd"),
        status=JobStatus.TESTING,
        versions=[Version.from_string("1.21.8")],
        proxy_type=ProxyType.VELOCITY,
        forwarding_method=ForwardingMethod.MODERN,
        plugins=["test-plugin.jar"],
        login_wait_timeout=30,
    )


@pytest.fixture
def mock_job_no_proxy() -> Job:
    """Create a mock Job with no proxy for testing."""
    return Job(
        job_id=JobId("test-job-2"),
        repo_url=RepoUrl("https://github.com/test-owner/test-repo.git"),
        ref="abc123def456",
        commit_hash=CommitHash("abc123def456789012345678901234567890abcd"),
        status=JobStatus.TESTING,
        versions=[Version.from_string("1.21.8")],
        proxy_type=ProxyType.NONE,
        forwarding_method=ForwardingMethod.NONE,
        plugins=None,
        login_wait_timeout=30,
    )


@pytest.fixture
def mock_proxy_manager():
    """Create a mock proxy manager."""
    manager = MagicMock()
    manager.start.return_value = MagicMock()
    manager.start.return_value.pid = 12345
    return manager


@pytest.fixture
def mock_artifact_repo():
    """Create a mock artifact repository."""
    repo = MagicMock(spec=ArtifactRepository)
    repo.get_cached_or_download.return_value = Path("/tmp/velocity-1.21.8.jar")
    return repo


@pytest.fixture
def mock_config_writer():
    """Create a mock config writer."""
    writer = MagicMock(spec=ConfigWriter)
    return writer


@pytest.fixture
def temp_builds_dir(tmp_path: Path) -> Path:
    """Create a temporary builds directory with a mock artifact."""
    builds_dir = tmp_path / "builds"
    # Path: builds / owner / ref / commit_hash / "pico_limbo"
    artifact_path = (
        builds_dir
        / "test-owner"
        / "abc123def456"  # ref from mock_job
        / "abc123def456789012345678901234567890abcd"  # commit_hash
        / "pico_limbo"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.touch()
    return builds_dir


# ============================================================================
# ServerContext tests
# ============================================================================


class TestServerContext:
    """Tests for the ServerContext class."""

    def test_context_manager_stops_servers(self):
        """ServerContext.__exit__ calls stop which runs cleanup."""
        cleanup_called = False

        def cleanup_fn() -> None:
            nonlocal cleanup_called
            cleanup_called = True

        mock_proxy = MagicMock()
        mock_proxy_proc = MagicMock()
        mock_pico_proc = MagicMock()

        with ServerContext(mock_proxy, mock_proxy_proc, mock_pico_proc, cleanup_fn):
            pass  # Exit context

        assert cleanup_called

    def test_context_manager_stop_calls_cleanup(self):
        """Explicit stop() calls the cleanup function."""
        cleanup_called = False

        def cleanup_fn() -> None:
            nonlocal cleanup_called
            cleanup_called = True

        ctx = ServerContext(
            MagicMock(), MagicMock(), MagicMock(), cleanup_fn
        )
        ctx.stop()
        assert cleanup_called

    def test_context_manager_with_none_values(self):
        """ServerContext handles None proxy and processes gracefully."""
        ctx = ServerContext(None, None, None, None)
        ctx.stop()  # Should not raise

    def test_context_manager_preserves_references(self):
        """ServerContext stores proxy, proxy_proc, and pico_limbo_proc."""
        proxy = MagicMock()
        proxy_proc = MagicMock()
        pico_proc = MagicMock()

        ctx = ServerContext(proxy, proxy_proc, pico_proc)

        assert ctx.proxy is proxy
        assert ctx.proxy_proc is proxy_proc
        assert ctx.pico_limbo_proc is pico_proc


# ============================================================================
# ServerSetupService tests
# ============================================================================


class TestServerSetupService:
    """Tests for the ServerSetupService class."""

    def test_setup_starts_proxy_and_pico_limbo(
        self,
        mock_job,
        temp_builds_dir,
        mock_proxy_manager,
        mock_artifact_repo,
        mock_config_writer,
        tmp_path,
    ):
        """Happy path: setup starts proxy and pico_limbo subprocess."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = mock_proxy_manager

        service = ServerSetupService(
            proxy_factory, mock_config_writer, mock_artifact_repo
        )

        proxy_dir = tmp_path / "proxy"
        proxy_dir.mkdir()
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        webui_dir = tmp_path / "webui"
        webui_dir.mkdir()

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            ctx = service.setup(
                mock_job,
                temp_builds_dir,
                proxy_dir,
                plugins_dir,
                webui_dir,
            )

            # Verify artifact was validated (path exists)
            assert ctx.pico_limbo_proc is not None
            assert ctx.proxy is mock_proxy_manager

            # Verify proxy.start was called
            mock_proxy_manager.start.assert_called_once()
            call_kwargs = mock_proxy_manager.start.call_args
            assert call_kwargs[1]["jar_path"] == Path("/tmp/velocity-1.21.8.jar")
            assert call_kwargs[1]["forwarding_secret"] == "sup3r-s3cr3t"
            assert call_kwargs[1]["plugins"] == ["test-plugin.jar"]

            # Verify config was written
            mock_config_writer.write_servers_dat.assert_called_once()
            mock_config_writer.write_options_txt.assert_called_once()

            # Verify pico_limbo subprocess was started
            mock_popen.assert_called_once()

    def test_setup_fails_when_artifact_missing(
        self,
        mock_job,
        tmp_path,
        mock_proxy_manager,
        mock_artifact_repo,
        mock_config_writer,
    ):
        """Setup raises RuntimeError when artifact is not found."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = mock_proxy_manager

        service = ServerSetupService(
            proxy_factory, mock_config_writer, mock_artifact_repo
        )

        # builds_dir doesn't contain the expected artifact path
        builds_dir = tmp_path / "nonexistent_builds"

        with pytest.raises(
            RuntimeError,
            match="Artifact not found",
        ):
            service.setup(
                mock_job,
                builds_dir,
                tmp_path / "proxy",
                tmp_path / "plugins",
                tmp_path / "webui",
            )

    def test_setup_skips_proxy_when_no_proxy(
        self,
        mock_job_no_proxy,
        temp_builds_dir,
        mock_artifact_repo,
        mock_config_writer,
        tmp_path,
    ):
        """Setup skips proxy creation when proxy_type is NONE."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = None

        service = ServerSetupService(
            proxy_factory, mock_config_writer, mock_artifact_repo
        )

        proxy_dir = tmp_path / "proxy"
        proxy_dir.mkdir()
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        webui_dir = tmp_path / "webui"
        webui_dir.mkdir()

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            ctx = service.setup(
                mock_job_no_proxy,
                temp_builds_dir,
                proxy_dir,
                plugins_dir,
                webui_dir,
            )

            # Proxy should be None
            assert ctx.proxy is None
            assert ctx.proxy_proc is None

            # PicoLimbo should still be started
            assert ctx.pico_limbo_proc is not None

            # Proxy factory should not have been used to create a proxy
            proxy_factory.create.assert_called_once()
            # Config should still be written
            mock_config_writer.write_servers_dat.assert_called_once()
            mock_config_writer.write_options_txt.assert_called_once()

    def test_context_manager_stops_servers_on_exit(
        self,
        mock_job,
        temp_builds_dir,
        mock_proxy_manager,
        mock_artifact_repo,
        mock_config_writer,
        tmp_path,
    ):
        """ServerContext.__exit__ properly cleans up proxy and pico_limbo."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = mock_proxy_manager

        service = ServerSetupService(
            proxy_factory, mock_config_writer, mock_artifact_repo
        )

        proxy_dir = tmp_path / "proxy"
        proxy_dir.mkdir()
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        webui_dir = tmp_path / "webui"
        webui_dir.mkdir()

        mock_proxy_proc = MagicMock()
        mock_proxy_proc.pid = 12345
        mock_proxy_proc.poll.return_value = None
        mock_proxy_manager.start.return_value = mock_proxy_proc

        mock_pico_proc = MagicMock()
        mock_pico_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_pico_proc):
            with ServerContext(
                proxy=mock_proxy_manager,
                proxy_proc=mock_proxy_proc,
                pico_limbo_proc=mock_pico_proc,
                cleanup_fn=lambda: service._cleanup(
                    mock_proxy_manager, mock_proxy_proc, mock_pico_proc
                ),
            ) as ctx:
                # Verify context is set up
                assert ctx.proxy is mock_proxy_manager
                assert ctx.proxy_proc is mock_proxy_proc
                assert ctx.pico_limbo_proc is mock_pico_proc

        # After exiting context, cleanup should have been called
        mock_pico_proc.terminate.assert_called_once()
        mock_proxy_manager.stop.assert_called_once_with(mock_proxy_proc)

    def test_setup_uses_correct_artifact_path(
        self,
        mock_job,
        temp_builds_dir,
        mock_proxy_manager,
        mock_artifact_repo,
        mock_config_writer,
        tmp_path,
    ):
        """Setup constructs the correct artifact path from job properties."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = mock_proxy_manager

        service = ServerSetupService(
            proxy_factory, mock_config_writer, mock_artifact_repo
        )

        # The artifact path should be:
        # builds_dir / owner / ref / commit_hash / "pico_limbo"
        expected_path = (
            temp_builds_dir
            / "test-owner"
            / "abc123def456"  # ref
            / "abc123def456789012345678901234567890abcd"  # commit_hash
            / "pico_limbo"
        )
        assert expected_path.exists()

        proxy_dir = tmp_path / "proxy"
        proxy_dir.mkdir()
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        webui_dir = tmp_path / "webui"
        webui_dir.mkdir()

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            ctx = service.setup(
                mock_job,
                temp_builds_dir,
                proxy_dir,
                plugins_dir,
                webui_dir,
            )

            # Should succeed because artifact exists
            assert ctx.pico_limbo_proc is not None

    def test_setup_starts_pico_limbo_with_env_vars(
        self,
        mock_job,
        temp_builds_dir,
        mock_proxy_manager,
        mock_artifact_repo,
        mock_config_writer,
        tmp_path,
    ):
        """Setup starts pico_limbo with correct environment variables."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = mock_proxy_manager

        service = ServerSetupService(
            proxy_factory, mock_config_writer, mock_artifact_repo
        )

        proxy_dir = tmp_path / "proxy"
        proxy_dir.mkdir()
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        webui_dir = tmp_path / "webui"
        webui_dir.mkdir()

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            service.setup(
                mock_job,
                temp_builds_dir,
                proxy_dir,
                plugins_dir,
                webui_dir,
            )

            # Verify subprocess.Popen was called with correct env vars
            call_kwargs = mock_popen.call_args[1]
            env = call_kwargs["env"]
            assert env["PICO_LIMBO_PROXY_PORT"] == "30066"
            assert env["PICO_LIMBO_MC_VERSION"] == "1.21.8"
            assert env["PICO_LIMBO_LOGIN_WAIT_TIMEOUT"] == "30"

    def test_cleanup_handles_already_dead_pico_limbo(
        self,
        mock_config_writer,
        mock_artifact_repo,
    ):
        """Cleanup doesn't crash when pico_limbo is already dead."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)

        service = ServerSetupService(
            proxy_factory, mock_config_writer, mock_artifact_repo
        )

        mock_proxy = MagicMock()
        mock_proxy_proc = MagicMock()
        mock_proxy_proc.poll.return_value = 0  # already dead

        # Should not raise
        service._cleanup(mock_proxy, mock_proxy_proc, None)

    def test_cleanup_handles_none_proxy(
        self,
        mock_config_writer,
        mock_artifact_repo,
    ):
        """Cleanup handles None proxy gracefully."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)

        service = ServerSetupService(
            proxy_factory, mock_config_writer, mock_artifact_repo
        )

        mock_pico_proc = MagicMock()
        mock_pico_proc.poll.return_value = None

        # Should not raise
        service._cleanup(None, None, mock_pico_proc)

        # PicoLimbo should be terminated
        mock_pico_proc.terminate.assert_called_once()
