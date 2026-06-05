"""Abstract base class for proxy managers."""

from abc import ABC, abstractmethod
from pathlib import Path
from subprocess import Popen
from typing import Optional


class ProxyManager(ABC):
    """Abstract base class for managing proxy processes."""

    @abstractmethod
    def download_if_needed(self) -> Path:
        """Download the proxy jar if not already cached.

        Returns:
            Path to the proxy jar file.
        """

    @abstractmethod
    def start(
        self, config_dir: Path, pico_limbo_port: int,
        jar_path: Path,
        forwarding_secret: str,
        plugins: list[str] | None = None,
        forwarding_method: str = "modern",
    ) -> Popen:
        """Start the proxy process.

        Args:
            config_dir: Directory where the proxy config will be written.
            pico_limbo_port: Port that PicoLimbo is running on (backend).

        Returns:
            The running proxy process.
        """

    @abstractmethod
    def stop(self, proc: Popen) -> None:
        """Stop the proxy process.

        Args:
            proc: The proxy process to stop.
        """

    @abstractmethod
    def wait_for_ready(
        self, proc: Popen, timeout: float = 30.0
    ) -> None:
        """Wait for the proxy to be ready to accept connections.

        Args:
            proc: The proxy process to wait for.
            timeout: Maximum time to wait in seconds.

        Raises:
            RuntimeError: If the proxy does not become ready within the timeout.
        """

    @abstractmethod
    def config_template(self, pico_limbo_port: int) -> dict:
        """Returns config values for the proxy.

        Args:
            pico_limbo_port: Port that PicoLimbo is running on.

        Returns:
            Dict of configuration values.
        """
