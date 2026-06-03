"""Velocity proxy implementation with PaperMC API integration."""

import json
import logging
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from subprocess import Popen

from .. import config
from ..infrastructure.artifact_repository import ArtifactRepository
from ..infrastructure.config_writer import ConfigWriter
from .base import ProxyManager

logger = logging.getLogger(__name__)

# Velocity config file name
VELOCITY_CONFIG_FILENAME = config.VELOCITY_CONFIG_FILENAME

# Velocity log patterns for readiness detection
LOGGING_ON_PATTERN = re.compile(r"Listening on", re.IGNORECASE)
DONE_PATTERN = re.compile(r"Done", re.IGNORECASE)

PLUGINS_DIR = config.PLUGINS_DIR


class VelocityProxyManager(ProxyManager):
    """Manages Velocity proxy lifecycle: download, configure, start, stop."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        artifact_repo: ArtifactRepository | None = None,
        config_writer: ConfigWriter | None = None,
    ) -> None:
        """Initialize the Velocity proxy manager.

        Args:
            cache_dir: Directory to cache Velocity jars.
                Defaults to ``config.PROXY_CACHE_DIR / "velocity"``.
            artifact_repo: Pre-configured ``ArtifactRepository``.
                If ``None``, one is created from *cache_dir* and
                ``config.VELOCITY_API_BASE``.
            config_writer: Pre-configured ``ConfigWriter`` for TOML output.
                If ``None``, a fresh instance is created.
        """
        self._cache_dir = cache_dir or config.PROXY_CACHE_DIR / "velocity"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_file = self._cache_dir / "metadata.json"
        self._artifact_repo = artifact_repo or ArtifactRepository(
            api_base=config.VELOCITY_API_BASE,
            cache_dir=self._cache_dir,
        )
        self._config_writer = config_writer or ConfigWriter()

    def download_if_needed(self) -> Path:
        """Download Velocity jar if not already cached.

        Uses PaperMC API to check for the latest stable build.
        If a cached jar exists with matching metadata, it is reused.

        Returns:
            Path to the Velocity jar file.
        """
        cached_jar, cached_mc_version = self._load_cached_version()
        latest_mc_version: str | None = None

        if cached_jar is not None and cached_jar.exists():
            # Check if the cached version is still the latest
            try:
                latest_mc_version = self._artifact_repo.get_latest_mc_version()
                if cached_mc_version == latest_mc_version:
                    logger.info("Using cached Velocity jar: %s", cached_jar)
                    return cached_jar
                logger.info(
                    "Cached version (%s) differs from latest (%s), downloading new version",
                    cached_mc_version,
                    latest_mc_version,
                )
            except RuntimeError:
                # If we can't reach the API, fall through to download
                logger.warning(
                    "Could not reach PaperMC API, falling back to download"
                )

        # Download the latest version
        if latest_mc_version is None:
            logger.info("No cached Velocity jar found, downloading latest...")
            latest_mc_version = self._artifact_repo.get_latest_mc_version()
        mc_version = latest_mc_version
        download_url = self._artifact_repo.get_download_url(mc_version)
        if download_url is None:
            raise RuntimeError(
                f"No stable Velocity build found for MC version {mc_version}"
            )

        jar_filename = f"velocity-{mc_version}.jar"
        jar_path = self._cache_dir / jar_filename

        logger.info(
            "Downloading Velocity from %s (MC %s)", download_url, mc_version
        )
        self._artifact_repo.download(download_url, jar_path)

        # Save metadata
        self._save_metadata(mc_version)

        logger.info("Downloaded Velocity jar: %s", jar_path)
        return jar_path

    def start(
        self,
        config_dir: Path,
        pico_limbo_port: int,
        jar_path: Path,
        forwarding_secret: str,
        plugins: list[str] | None = None,
        forwarding_method: str = "modern",
    ) -> Popen:
        """Start the Velocity proxy process.

        Args:
            config_dir: Directory where velocity.toml will be written.
            pico_limbo_port: Port that PicoLimbo is running on.
            jar_path: Path to the Velocity jar file.
            forwarding_secret: Forwarding secret for player-info forwarding.
            plugins: List of plugin names to copy into plugins folder.
            forwarding_method: Player info forwarding mode
                (none, legacy, bungeeguard, modern).

        Returns:
            The running Velocity process.
        """
        # Generate and write config
        config_path = config_dir / VELOCITY_CONFIG_FILENAME
        config_dict = self.config_template(pico_limbo_port, forwarding_method)
        self._config_writer.write_velocity_toml(config_path, config_dict)
        logger.info("Wrote Velocity config to %s", config_path)

        # Write forwarding secret file
        secret_path = config_dir / "forwarding.secret"
        secret_path.write_text(forwarding_secret)
        logger.info("Wrote Velocity forwarding secret to %s", secret_path)

        # Copy plugins
        self._copy_plugins(config_dir, plugins)

        logger.info(
            "Starting Velocity from %s with config %s",
            jar_path,
            config_path,
        )

        # Start Velocity as a subprocess
        proc = subprocess.Popen(
            ["java", "-jar", str(jar_path)],
            cwd=str(config_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        logger.info("Velocity process started with PID %d", proc.pid)
        return proc

    def stop(self, proc: Popen) -> None:
        """Stop the Velocity proxy process.

        Args:
            proc: The Velocity process to stop.
        """
        if proc and proc.poll() is None:
            logger.info("Stopping Velocity (PID %d)", proc.pid)
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Velocity did not terminate gracefully, killing")
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.error("Velocity failed to be killed")

    def _copy_plugins(self, config_dir: Path, plugins: list[str] | None = None) -> None:
        """Copy plugin .jar files into the proxy's plugins directory.

        Args:
            config_dir: Directory where velocity.toml is written (parent of plugins/).
            plugins: List of plugin names to copy.
        """
        if not plugins:
            return

        plugins_dir = config_dir / "plugins"
        plugins_dir.mkdir(exist_ok=True)

        import shutil

        for plugin_name in plugins:
            source = PLUGINS_DIR / plugin_name
            dest = plugins_dir / plugin_name
            if source.exists():
                shutil.copy2(str(source), str(dest))
                logger.info("Copied plugin %s to %s", plugin_name, dest)
            else:
                logger.warning("Plugin file %s not found in %s, skipping", plugin_name, PLUGINS_DIR)

    def wait_for_ready(
        self, proc: Popen, timeout: float = 30.0
    ) -> None:
        """Wait for Velocity to be ready to accept connections.

        Reads Velocity's stdout line by line and checks for readiness patterns.

        Args:
            proc: The Velocity process to wait for.
            timeout: Maximum time to wait in seconds.

        Raises:
            RuntimeError: If the proxy does not become ready within the timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline and proc.poll() is None:
            line = proc.stdout.readline()
            if line:
                logger.info("Velocity: %s", line.rstrip())
                if LOGGING_ON_PATTERN.search(line):
                    logger.info("Velocity: detected 'Listening on' — proxy is ready")
                    return
                if DONE_PATTERN.search(line):
                    logger.info("Velocity: detected 'Done' — proxy is ready")
                    return
            time.sleep(0.1)

        # If we get here, either the process died or timeout was hit
        if proc.poll() is not None:
            raise RuntimeError(
                f"Velocity process exited with code {proc.returncode}"
            )

        raise RuntimeError(
            f"Velocity did not become ready within {timeout} seconds"
        )

    def config_template(self, pico_limbo_port: int, forwarding_method: str = "modern") -> dict:
        """Returns config values for Velocity.

        Args:
            pico_limbo_port: Port that PicoLimbo is running on.
            forwarding_method: Player info forwarding mode (none, legacy, bungeeguard, modern).

        Returns:
            Dict of configuration values for the proxy.
        """
        return {
            "bind": "0.0.0.0:25565",
            "online-mode": False,
            "player-info-forwarding-mode": forwarding_method.upper(),
            "forwarding-secret-file": "forwarding.secret",
            "servers": {
                "limbo": f"127.0.0.1:{pico_limbo_port}",
                "try": ["limbo"],
            },
            "forced-hosts": {},
        }

    def _load_cached_version(self) -> tuple[Path | None, str | None]:
        """Load the cached version info from metadata.

        Returns:
            A tuple of (cached_jar_path, minecraft_version), or (None, None) if no cache.
        """
        if not self._metadata_file.exists():
            return None, None

        try:
            metadata = json.loads(self._metadata_file.read_text())
            version = metadata.get("minecraft_version")
            if not version:
                return None, None
            jar_path = self._cache_dir / f"velocity-{version}.jar"
            return jar_path, version
        except (json.JSONDecodeError, OSError):
            return None, None

    def _save_metadata(self, mc_version: str) -> None:
        """Save metadata about the cached Velocity jar.

        Args:
            mc_version: The Minecraft version of the cached jar.
        """
        metadata = {
            "version": mc_version,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "minecraft_version": mc_version,
        }
        self._metadata_file.write_text(json.dumps(metadata))
