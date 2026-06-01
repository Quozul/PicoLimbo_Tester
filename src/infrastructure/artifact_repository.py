"""Artifact repository — anti-corruption layer for PaperMC API downloads.

Provides a clean ``ArtifactRepository`` class that wraps all PaperMC API calls
and artifact download/caching logic behind a simple interface.  All HTTP
requests are isolated here so the rest of the codebase never invokes ``httpx``
directly for artifact fetching.
"""

import logging
from pathlib import Path

import httpx

from .. import config

logger = logging.getLogger(__name__)


class ArtifactRepository:
    """Anti-corruption layer for artifact downloads (PaperMC API).

    Parameters
    ----------
    api_base : str
        PaperMC API base URL (e.g. ``https://fill.papermc.io/v3/projects/velocity``).
    cache_dir : Path
        Directory where downloaded JARs are cached.
    http : httpx.Client
        Reusable HTTP client.  If ``None``, a new ``httpx.Client()`` is created
        internally.  Injecting a client is useful for testing.
    """

    def __init__(
        self,
        api_base: str,
        cache_dir: Path,
        http: httpx.Client | None = None,
    ) -> None:
        self._api_base = api_base
        self._cache_dir = cache_dir
        self._http = http or httpx.Client()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_latest_mc_version(self) -> str:
        """Fetch the latest Minecraft version that has a stable Velocity build.

        Returns
        -------
        str
            The latest Minecraft version string.

        Raises
        ------
        RuntimeError
            If the API request fails or no versions are returned.
        """
        logger.debug("Fetching latest Velocity MC version from %s/versions", self._api_base)
        try:
            resp = self._http.get(f"{self._api_base}/versions", timeout=30.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Failed to fetch Velocity versions from PaperMC API: {exc}")
        data = resp.json()
        versions_list = data.get("versions", [])
        if not versions_list:
            raise RuntimeError("No Minecraft versions found for Velocity on PaperMC API")
        latest = versions_list[0]["version"]["id"]
        logger.debug("Latest MC version: %s", latest)
        return latest

    def get_download_url(self, mc_version: str) -> str | None:
        """Get the download URL for the latest stable Velocity build.

        Parameters
        ----------
        mc_version : str
            Minecraft version to look up (e.g. ``"1.21.8"``).

        Returns
        -------
        str | None
            The download URL, or ``None`` if no stable build is found.

        Raises
        ------
        RuntimeError
            If the API request fails.
        """
        logger.debug(
            "Fetching Velocity builds for MC %s from %s/versions/%s/builds",
            mc_version,
            self._api_base,
            mc_version,
        )
        try:
            resp = self._http.get(
                f"{self._api_base}/versions/{mc_version}/builds", timeout=30.0
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Failed to fetch Velocity builds for MC {mc_version}: {exc}"
            )
        builds = resp.json()

        if not isinstance(builds, list):
            logger.warning("Expected list of builds, got %s", type(builds))
            return None

        stable_builds = [b for b in builds if b.get("channel") == "STABLE"]
        if not stable_builds:
            logger.warning("No stable builds found for MC version %s", mc_version)
            return None

        latest = stable_builds[0]
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

    def download(self, url: str, dest: Path) -> Path:
        """Download a file from *url* to *dest*.

        On failure the destination file is removed (partial download cleanup).

        Parameters
        ----------
        url : str
            URL to download from.
        dest : Path
            Destination path for the downloaded file.

        Returns
        -------
        Path
            The destination path (same as *dest*).

        Raises
        ------
        RuntimeError
            If the download fails.
        """
        logger.debug("Downloading %s to %s", url, dest)
        try:
            resp = self._http.get(url, timeout=120.0, follow_redirects=True)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            logger.debug("Downloaded %d bytes to %s", len(resp.content), dest)
            return dest
        except httpx.HTTPError as exc:
            if dest.exists():
                dest.unlink()
                logger.debug("Cleaned up partial download at %s", dest)
            raise RuntimeError(f"Failed to download {url}: {exc}")

    def get_cached_or_download(self, mc_version: str) -> Path:
        """Get a cached JAR if available, otherwise download it.

        Parameters
        ----------
        mc_version : str
            Minecraft version to fetch.

        Returns
        -------
        Path
            Path to the cached or freshly downloaded JAR.

        Raises
        ------
        RuntimeError
            If no stable build exists for the given version or download fails.
        """
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cached = self._cache_dir / f"velocity-{mc_version}.jar"
        if cached.exists():
            logger.info("Using cached Velocity jar: %s", cached)
            return cached

        url = self.get_download_url(mc_version)
        if not url:
            raise RuntimeError(f"No stable build for MC {mc_version}")

        logger.info("Downloading Velocity (MC %s) from %s", mc_version, url)
        return self.download(url, cached)
