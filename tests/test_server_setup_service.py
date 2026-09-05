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
def mock_config_writer():
    """Create a mock config writer."""
    writer = MagicMock(spec=ConfigWriter)
    return writer


@pytest.fixture
def temp_builds_dir(tmp_path: Path) -> Path:
    """Create a temporary builds directory with a mock artifact."""
    builds_dir = tmp_path / "builds"
    # Path: builds / commit_hash[:8] / "latest" / "pico_limbo"
    artifact_path = (
        builds_dir
        / "abc123de"  # commit_hash[:8]
        / "latest"
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
        mock_config_writer,
        tmp_path,
    ):
        """Happy path: setup starts proxy and pico_limbo subprocess."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = mock_proxy_manager

        service = ServerSetupService(
            proxy_factory, mock_config_writer
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

            # Verify proxy.download_if_needed was called
            mock_proxy_manager.download_if_needed.assert_called_once()
            # Verify proxy.start was called
            mock_proxy_manager.start.assert_called_once()
            assert mock_proxy_manager.start.call_args[1]["plugins"] == ["test-plugin.jar"]

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
        mock_config_writer,
    ):
        """Setup raises RuntimeError when artifact is not found."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = mock_proxy_manager

        service = ServerSetupService(
            proxy_factory, mock_config_writer
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
        mock_config_writer,
        tmp_path,
    ):
        """Setup skips proxy creation when proxy_type is NONE."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = None

        service = ServerSetupService(
            proxy_factory, mock_config_writer
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
        mock_config_writer,
        tmp_path,
    ):
        """ServerContext.__exit__ properly cleans up proxy and pico_limbo."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = mock_proxy_manager

        service = ServerSetupService(
            proxy_factory, mock_config_writer
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
        mock_config_writer,
        tmp_path,
    ):
        """Setup constructs the correct artifact path from job properties."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = mock_proxy_manager

        service = ServerSetupService(
            proxy_factory, mock_config_writer
        )

        # The artifact path should be:
        # builds_dir / commit_hash[:8] / "latest" / "pico_limbo"
        expected_path = (
            temp_builds_dir
            / "abc123de"  # commit_hash[:8]
            / "latest"
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
        mock_config_writer,
        tmp_path,
    ):
        """Setup starts pico_limbo with correct environment variables."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = mock_proxy_manager

        service = ServerSetupService(
            proxy_factory, mock_config_writer
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
    ):
        """Cleanup doesn't crash when pico_limbo is already dead."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)

        service = ServerSetupService(
            proxy_factory, mock_config_writer
        )

        mock_proxy = MagicMock()
        mock_proxy_proc = MagicMock()
        mock_proxy_proc.poll.return_value = 0  # already dead

        # Should not raise
        service._cleanup(mock_proxy, mock_proxy_proc, None)

    def test_cleanup_handles_none_proxy(
        self,
        mock_config_writer,
    ):
        """Cleanup handles None proxy gracefully."""
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)

        service = ServerSetupService(
            proxy_factory, mock_config_writer
        )

        mock_pico_proc = MagicMock()
        mock_pico_proc.poll.return_value = None

        # Should not raise
        service._cleanup(None, None, mock_pico_proc)

        # PicoLimbo should be terminated
        mock_pico_proc.terminate.assert_called_once()


# ============================================================================
# ServerSetupService — schematic + server.toml
# ============================================================================


class TestServerSetupSchematic:
    """Schematic staging and PicoLimbo server.toml generation."""

    @pytest.fixture
    def service(self, mock_config_writer):
        from src.proxy.factory import ProxyFactory

        proxy_factory = MagicMock(spec=ProxyFactory)
        proxy_factory.create.return_value = None
        return ServerSetupService(proxy_factory, mock_config_writer)

    @pytest.fixture
    def dirs(self, tmp_path):
        proxy_dir = tmp_path / "proxy"
        proxy_dir.mkdir()
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        webui_dir = tmp_path / "webui"
        webui_dir.mkdir()
        return proxy_dir, plugins_dir, webui_dir

    @pytest.fixture
    def schematics_dir(self, tmp_path):
        schematics = tmp_path / "schematics"
        schematics.mkdir()
        return schematics

    def test_writes_server_toml_without_schematic(
        self, service, mock_job_no_proxy, temp_builds_dir, dirs, mock_config_writer
    ):
        """Direct mode: server.toml has empty schematic, default view distance, no bind."""
        from src.infrastructure.config_writer import build_server_config

        proxy_dir, plugins_dir, webui_dir = dirs
        with patch("subprocess.Popen"):
            service.setup(mock_job_no_proxy, temp_builds_dir, proxy_dir, plugins_dir, webui_dir)

        expected = build_server_config(schematic_file=None, view_distance=None)
        mock_config_writer.write_server_toml.assert_called_once_with(
            proxy_dir / "server.toml", expected
        )
        # Direct mode keeps the default bind — the key must be absent
        assert "bind" not in expected

    def test_writes_server_toml_with_schematic_and_view_distance(
        self,
        service,
        temp_builds_dir,
        dirs,
        mock_config_writer,
        schematics_dir,
    ):
        """Schematic path (absolute, staged) and view distance land in server.toml."""
        from src.infrastructure.config_writer import build_server_config

        job = _make_schematic_job(schematic_file="spawn.schem", view_distance=8)
        (schematics_dir / "spawn.schem").write_bytes(b"fake-schem")
        proxy_dir, plugins_dir, webui_dir = dirs

        with patch(
            "src.application.server_setup_service.SCHEMATICS_DIR", schematics_dir
        ), patch("subprocess.Popen"):
            service.setup(job, temp_builds_dir, proxy_dir, plugins_dir, webui_dir)

        expected = build_server_config(
            schematic_file=str(proxy_dir / "spawn.schem"), view_distance=8
        )
        mock_config_writer.write_server_toml.assert_called_once_with(
            proxy_dir / "server.toml", expected
        )

    def test_stages_schematic_into_proxy_dir(
        self, service, temp_builds_dir, dirs, schematics_dir
    ):
        """The uploaded .schem is copied next to server.toml."""
        job = _make_schematic_job(schematic_file="spawn.schem")
        (schematics_dir / "spawn.schem").write_bytes(b"fake-schem")
        proxy_dir, plugins_dir, webui_dir = dirs

        with patch(
            "src.application.server_setup_service.SCHEMATICS_DIR", schematics_dir
        ), patch("subprocess.Popen"):
            service.setup(job, temp_builds_dir, proxy_dir, plugins_dir, webui_dir)

        staged = proxy_dir / "spawn.schem"
        assert staged.is_file()
        assert staged.read_bytes() == b"fake-schem"

    def test_missing_schematic_fails_before_pico_limbo_starts(
        self, service, mock_proxy_manager, temp_builds_dir, dirs, schematics_dir
    ):
        """A schematic that was deleted after job creation fails the job clearly."""
        job = _make_schematic_job(schematic_file="gone.schem")
        proxy_dir, plugins_dir, webui_dir = dirs

        with patch(
            "src.application.server_setup_service.SCHEMATICS_DIR", schematics_dir
        ), patch("subprocess.Popen") as mock_popen:
            with pytest.raises(RuntimeError, match="Schematic file not found"):
                service.setup(job, temp_builds_dir, proxy_dir, plugins_dir, webui_dir)

        mock_popen.assert_not_called()

    def test_proxy_mode_binds_internal_port(
        self,
        service,
        mock_job,
        temp_builds_dir,
        dirs,
        mock_config_writer,
    ):
        """Behind the proxy, PicoLimbo must bind the internal port (proxy owns 25565)."""
        proxy_dir, plugins_dir, webui_dir = dirs
        with patch("subprocess.Popen"):
            service.setup(mock_job, temp_builds_dir, proxy_dir, plugins_dir, webui_dir)

        args, _ = mock_config_writer.write_server_toml.call_args
        assert args[1]["bind"] == "127.0.0.1:30066"

    def test_pico_limbo_started_with_config_flag(
        self, service, mock_job_no_proxy, temp_builds_dir, dirs
    ):
        """The binary is launched with --config pointing at the generated server.toml."""
        proxy_dir, plugins_dir, webui_dir = dirs
        with patch("subprocess.Popen") as mock_popen:
            service.setup(mock_job_no_proxy, temp_builds_dir, proxy_dir, plugins_dir, webui_dir)

        cmd = mock_popen.call_args[0][0]
        assert cmd[-2:] == ["--config", str(proxy_dir / "server.toml")]


def _make_schematic_job(**overrides):
    """Build a Job with schematic fields for setup tests."""
    from src.domain.job import Job
    from src.domain.value_objects import (
        CommitHash,
        ForwardingMethod,
        JobId,
        JobStatus,
        ProxyType,
        RepoUrl,
        Version,
    )

    defaults = {
        "job_id": JobId("schem-job"),
        "repo_url": RepoUrl("https://github.com/test-owner/test-repo.git"),
        "ref": "abc123def456",
        "commit_hash": CommitHash("abc123def456789012345678901234567890abcd"),
        "status": JobStatus.TESTING,
        "versions": [Version.from_string("1.21.8")],
        "proxy_type": ProxyType.NONE,
        "forwarding_method": ForwardingMethod.NONE,
        "plugins": None,
        "login_wait_timeout": 30,
        "schematic_file": None,
        "view_distance": None,
    }
    defaults.update(overrides)
    return Job(**defaults)
