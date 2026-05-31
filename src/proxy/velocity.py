"""Velocity proxy implementation with PaperMC API integration."""

import json
import logging
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from subprocess import Popen

import httpx

from .base import ProxyManager

logger = logging.getLogger(__name__)

# PaperMC API base URL for Velocity
VELOCITY_API_BASE = "https://fill.papermc.io/v3/projects/velocity"

# Default proxy cache directory
# Use XDG_CACHE_HOME or ~/.cache if /app is not writable (e.g. local dev)
def _get_default_proxy_cache_dir() -> Path:
    """Determine the default proxy cache directory."""
    import os

    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache) / "pico_limbo" / "proxies"
    home = os.environ.get("HOME")
    if home:
        return Path(home) / ".cache" / "pico_limbo" / "proxies"
    return Path("/app/cache/proxies")


PROXY_CACHE_DIR = _get_default_proxy_cache_dir()

# Velocity config file name
VELOCITY_CONFIG_FILENAME = "velocity.toml"

# Velocity log patterns for readiness detection
LOGGING_ON_PATTERN = re.compile(r"Listening on", re.IGNORECASE)
DONE_PATTERN = re.compile(r"Done", re.IGNORECASE)


class VelocityProxyManager(ProxyManager):
    """Manages Velocity proxy lifecycle: download, configure, start, stop."""

    def __init__(self, cache_dir: Path | None = None):
        """Initialize the Velocity proxy manager.

        Args:
            cache_dir: Directory to cache Velocity jars. Defaults to /app/cache/proxies/velocity/.
        """
        self._cache_dir = cache_dir or PROXY_CACHE_DIR / "velocity"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_file = self._cache_dir / "metadata.json"

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
                latest_mc_version = self._get_latest_mc_version()
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
            latest_mc_version = self._get_latest_mc_version()
        mc_version = latest_mc_version
        download_url = self._get_velocity_download_url(mc_version)
        if download_url is None:
            raise RuntimeError(
                f"No stable Velocity build found for MC version {mc_version}"
            )

        jar_filename = f"velocity-{mc_version}.jar"
        jar_path = self._cache_dir / jar_filename

        logger.info(
            "Downloading Velocity from %s (MC %s)", download_url, mc_version
        )
        self._download_file(download_url, jar_path)

        # Save metadata
        self._save_metadata(mc_version)

        logger.info("Downloaded Velocity jar: %s", jar_path)
        return jar_path

    def start(self, config_dir: Path, pico_limbo_port: int, forwarding_method: str = "modern", forwarding_secret: str = "sup3r-s3cr3t") -> Popen:
        """Start the Velocity proxy process.

        Args:
            config_dir: Directory where velocity.toml will be written.
            pico_limbo_port: Port that PicoLimbo is running on.
            forwarding_method: Player info forwarding mode (none, legacy, bungeeguard, modern).
            forwarding_secret: Secret for forwarding authentication.

        Returns:
            The running Velocity process.
        """
        # Generate and write config
        config_path = config_dir / VELOCITY_CONFIG_FILENAME
        config_content = self._generate_config(pico_limbo_port, forwarding_method, forwarding_secret)
        config_path.write_text(config_content)
        logger.info("Wrote Velocity config to %s", config_path)

        # Write forwarding secret file
        secret_path = config_dir / "forwarding.secret"
        secret_path.write_text(forwarding_secret)
        logger.info("Wrote Velocity forwarding secret to %s", secret_path)

        jar_path = self.download_if_needed()
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
            # Read any remaining output
            try:
                remaining = proc.stdout.read() if proc.stdout else ""
            except Exception:
                remaining = ""
            if remaining:
                logger.warning("Velocity output:\n%s", remaining)
            raise RuntimeError(
                f"Velocity process exited with code {proc.returncode}"
            )

        raise RuntimeError(
            f"Velocity did not become ready within {timeout} seconds"
        )

    def config_template(self, pico_limbo_port: int, forwarding_method: str = "modern", forwarding_secret: str = "sup3r-s3cr3t") -> dict:
        """Returns config values for Velocity.

        Args:
            pico_limbo_port: Port that PicoLimbo is running on.
            forwarding_method: Player info forwarding mode (none, legacy, bungeeguard, modern).
            forwarding_secret: Secret for forwarding authentication.

        Returns:
            Dict of configuration values for the proxy.
        """
        return {
            "bind": "0.0.0.0:25565",
            "online_mode": False,
            "player_info_forwarding_mode": forwarding_method.upper(),
            "servers": {
                "limbo": f"127.0.0.1:{pico_limbo_port}",
                "try": ["limbo"],
            },
        }

    @staticmethod
    def _toml_value(value: object) -> str:
        """Convert a Python value to a TOML-literal string.

        TOML booleans are lowercase (true/false), and lists use
        bracket notation.
        """
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list):
            items = ", ".join(
                VelocityProxyManager._toml_value(v) for v in value
            )
            return f"[{items}]"
        if isinstance(value, str):
            # Use TOML basic string (double-quoted)
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return str(value)

    def _generate_config(self, pico_limbo_port: int, forwarding_method: str = "modern", forwarding_secret: str = "sup3r-s3cr3t") -> str:
        """Generate a TOML config for Velocity.

        Args:
            pico_limbo_port: Port that PicoLimbo is running on.
            forwarding_method: Player info forwarding mode.
            forwarding_secret: Secret for forwarding authentication.

        Returns:
            TOML configuration string.
        """
        config = self.config_template(pico_limbo_port, forwarding_method, forwarding_secret)
        return (
            f'bind = {self._toml_value(config["bind"])}\n'
            f'online-mode = {self._toml_value(config["online_mode"])}\n'
            f'player-info-forwarding-mode = {self._toml_value(config["player_info_forwarding_mode"])}\n'
            f'forwarding-secret-file = "forwarding.secret"\n'
            f'\n'
            f'[servers]\n'
            f'limbo = {self._toml_value(config["servers"]["limbo"])}\n'
            f'try = {self._toml_value(config["servers"]["try"])}\n'
            f'\n'
            f'[forced-hosts]\n'
        )

    def _get_latest_mc_version(self) -> str:
        """Get the latest Minecraft version that has a stable Velocity build.

        Returns:
            The latest Minecraft version string.
        """
        logger.debug(
            "Fetching latest Velocity MC version from %s/versions",
            VELOCITY_API_BASE,
        )
        try:
            resp = httpx.get(f"{VELOCITY_API_BASE}/versions", timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            # API v3 returns {"versions": [{"version": {"id": "3.5.0"}, "builds": [...]}, ...]}
            versions_list = data.get("versions", [])
            if not versions_list:
                raise RuntimeError("No Minecraft versions found for Velocity on PaperMC API")
            logger.debug("Available Velocity versions (first 5): %s", [v.get("version", {}).get("id") for v in versions_list[:5]])
            return versions_list[0]["version"]["id"]
        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to fetch Velocity versions from PaperMC API: {e}")

    def _get_velocity_download_url(self, mc_version: str) -> str | None:
        """Get the download URL for the latest stable Velocity build.

        Args:
            mc_version: Minecraft version to get the build for.

        Returns:
            The download URL, or None if no stable build found.
        """
        logger.debug(
            "Fetching Velocity builds for MC %s from %s/versions/%s/builds",
            mc_version,
            VELOCITY_API_BASE,
            mc_version,
        )
        try:
            resp = httpx.get(
                f"{VELOCITY_API_BASE}/versions/{mc_version}/builds", timeout=30.0
            )
            resp.raise_for_status()
            builds = resp.json()
            # API v3 returns a list: [{"id": 102, "channel": "STABLE", "downloads": {"server:default": {"url": "..."}}, ...}]
            if not isinstance(builds, list):
                logger.warning("Expected list of builds, got %s", type(builds))
                return None
            if not builds:
                logger.warning("No builds found for MC version %s", mc_version)
                return None

            # Find the latest stable build (list is ordered by ID descending)
            stable_builds = [b for b in builds if b.get("channel") == "STABLE"]
            if not stable_builds:
                logger.warning("No stable builds found for MC version %s", mc_version)
                return None

            latest = stable_builds[0]
            # Download URL is at downloads["server:default"]["url"]
            download_info = latest.get("downloads", {}).get("server:default")
            if not download_info:
                logger.warning(
                    "No default server download found for Velocity build %s",
                    latest.get("id"),
                )
                return None

            url = download_info.get("url")
            if not url:
                logger.warning("No download URL found for build %s", latest.get("id"))
                return None

            logger.debug("Velocity build %s: %s", latest.get("id"), url)
            return url
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"Failed to fetch Velocity builds for MC {mc_version}: {e}"
            )

    def _download_file(self, url: str, dest: Path) -> None:
        """Download a file from a URL.

        Args:
            url: The URL to download from.
            dest: The destination path for the downloaded file.
        """
        try:
            resp = httpx.get(url, timeout=120.0, follow_redirects=True)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            logger.debug("Downloaded %d bytes to %s", len(resp.content), dest)
        except httpx.HTTPError as e:
            # Clean up partial download
            if dest.exists():
                dest.unlink()
            raise RuntimeError(f"Failed to download {url}: {e}")

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
