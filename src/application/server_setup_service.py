"""Server setup domain service.

Orchestrates proxy, config, and PicoLimbo subprocess lifecycle
using ProxyFactory, ConfigWriter, and ArtifactRepository.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..proxy.base import ProxyManager

from ..config import (
    PICO_LIMBO_INTERNAL_PORT,
    SERVER_ADDRESS,
    _FORWARDING_SECRET,
)
from ..domain.job import Job
from ..domain.value_objects import ProxyType
from ..infrastructure.artifact_repository import ArtifactRepository
from ..infrastructure.config_writer import ConfigWriter, ServerEntry
from ..proxy.factory import ProxyFactory
from .server_context import ServerContext

logger = logging.getLogger(__name__)

__all__ = ["ServerSetupService"]


class ServerSetupService:
    """Domain service for setting up proxy, config, and PicoLimbo subprocess.

    Uses ProxyFactory, ConfigWriter, ArtifactRepository.

    Parameters
    ----------
    proxy_factory : ProxyFactory
        Factory for creating proxy manager instances.
    config_writer : ConfigWriter
        Writer for configuration files.
    artifact_repo : ArtifactRepository
        Repository for downloading and caching artifacts.
    """

    def __init__(
        self,
        proxy_factory: ProxyFactory,
        config_writer: ConfigWriter,
        artifact_repo: ArtifactRepository,
    ) -> None:
        self._proxy_factory = proxy_factory
        self._config = config_writer
        self._artifact_repo = artifact_repo

    def setup(
        self,
        job: Job,
        builds_dir: Path,
        proxy_dir: Path,
        plugins_dir: Path,
        webui_dir: Path,
    ) -> ServerContext:
        """Set up proxy, config, and PicoLimbo subprocess.

        Parameters
        ----------
        job : Job
            The job being executed.
        builds_dir : Path
            Directory containing build artifacts.
        proxy_dir : Path
            Directory for proxy configuration and jar.
        plugins_dir : Path
            Directory for plugins.
        webui_dir : Path
            Directory for web UI.

        Returns
        -------
        ServerContext
            Context manager for the running servers.

        Raises
        ------
        RuntimeError
            If artifact not found or setup fails.
        """
        # Validate artifact
        commit_hash = job.commit_hash.value
        artifact_path = (
            builds_dir / job.owner / job.ref / commit_hash / "pico_limbo"
        )
        if not artifact_path.exists():
            raise RuntimeError(f"Artifact not found: {artifact_path}")

        # Start proxy if needed
        proxy = self._proxy_factory.create(job.proxy_type)
        proxy_proc: subprocess.Popen[str] | None = None
        pico_limbo_proc: subprocess.Popen[str] | None = None

        if job.proxy_type != ProxyType.NONE and proxy is not None:
            # Download jar if needed
            jar_path = self._artifact_repo.get_cached_or_download(job.mc_version)
            # Start proxy
            proxy_proc = proxy.start(
                config_dir=proxy_dir,
                pico_limbo_port=PICO_LIMBO_INTERNAL_PORT,
                jar_path=jar_path,
                forwarding_secret=_FORWARDING_SECRET,
                plugins=job.plugins or [],
            )

        # Write config files
        self._config.write_servers_dat(
            proxy_dir / "servers.dat",
            [ServerEntry(address=SERVER_ADDRESS, name="pico_limbo")],
        )
        self._config.write_options_txt(
            proxy_dir / "options.txt",
            job.mc_version,
        )

        # Start PicoLimbo subprocess
        pico_limbo_proc = self._start_pico_limbo(
            artifact_path=artifact_path,
            proxy_port=PICO_LIMBO_INTERNAL_PORT,
            mc_version=str(job.mc_version),
            login_wait_timeout=job.login_wait_timeout,
        )

        return ServerContext(
            proxy,
            proxy_proc,
            pico_limbo_proc,
            lambda: self._cleanup(proxy, proxy_proc, pico_limbo_proc),
        )

    def _start_pico_limbo(
        self,
        artifact_path: Path,
        proxy_port: int,
        mc_version: str,
        login_wait_timeout: int,
    ) -> subprocess.Popen[str]:
        """Start PicoLimbo subprocess.

        Parameters
        ----------
        artifact_path : Path
            Path to the PicoLimbo binary.
        proxy_port : int
            Port the proxy is listening on.
        mc_version : str
            Minecraft version string.
        login_wait_timeout : int
            Login wait timeout in seconds.

        Returns
        -------
        subprocess.Popen[str]
            The running PicoLimbo process.
        """
        env = os.environ.copy()
        env["PICO_LIMBO_PROXY_PORT"] = str(proxy_port)
        env["PICO_LIMBO_MC_VERSION"] = mc_version
        env["PICO_LIMBO_LOGIN_WAIT_TIMEOUT"] = str(login_wait_timeout)

        proc = subprocess.Popen(
            [str(artifact_path)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return proc

    def _cleanup(
        self,
        proxy: "ProxyManager | None",
        proxy_proc: subprocess.Popen[str] | None,
        pico_limbo_proc: subprocess.Popen[str] | None,
    ) -> None:
        """Cleanup proxy and PicoLimbo subprocess.

        Parameters
        ----------
        proxy : ProxyManager | None
            The proxy manager instance.
        proxy_proc : subprocess.Popen[str] | None
            The proxy process.
        pico_limbo_proc : subprocess.Popen[str] | None
            The PicoLimbo process.
        """
        # Kill PicoLimbo first
        if pico_limbo_proc and pico_limbo_proc.poll() is None:
            logger.info("Terminating PicoLimbo subprocess")
            pico_limbo_proc.terminate()
            try:
                pico_limbo_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("PicoLimbo did not terminate, killing")
                pico_limbo_proc.kill()

        # Stop the proxy (if any)
        self._stop_proxy(proxy, proxy_proc)

    def _stop_proxy(
        self,
        proxy: ProxyManager | None,
        proxy_proc: subprocess.Popen[str] | None,
    ) -> None:
        """Stop the proxy process.

        Uses the proxy manager's stop method when available,
        falls back to direct process termination.

        Parameters
        ----------
        proxy : ProxyManager | None
            The proxy manager instance.
        proxy_proc : subprocess.Popen[str] | None
            The proxy process.
        """
        if proxy is None:
            return

        if hasattr(proxy, "stop") and proxy_proc is not None:
            try:
                proxy.stop(proxy_proc)
                logger.info("Stopped proxy via manager")
            except Exception:
                logger.warning("Proxy manager stop failed, using direct kill")
                self._direct_kill(proxy_proc)
        elif proxy_proc is not None:
            self._direct_kill(proxy_proc)

    def _direct_kill(self, proc: subprocess.Popen[str]) -> None:
        """Directly kill a process.

        Parameters
        ----------
        proc : subprocess.Popen[str]
            The process to kill.
        """
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
