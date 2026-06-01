"""Artifact storage — repository pattern for build artifacts.

Provides a clean ``ArtifactStorage`` class that handles storing and retrieving
build artifacts on the file system.  All file operations are isolated here so
the rest of the codebase never invokes ``shutil`` or ``Path`` directly for
artifact management.
"""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class ArtifactStorage:
    """Repository pattern for build artifacts (file system).

    Artifacts are stored under ``{builds_dir}/{commit_hash[:8]}/{version}/``.

    Parameters
    ----------
    builds_dir : Path
        Base directory where build artifacts are stored.
    """

    def __init__(self, builds_dir: Path) -> None:
        self._builds_dir = builds_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, source: Path, commit_hash: str, version: str = "latest") -> Path:
        """Store a build artifact.

        Copies *source* into the builds directory under a path derived from
        the commit hash and optional version label.

        Parameters
        ----------
        source : Path
            Path to the file to store.
        commit_hash : str
            40-character hexadecimal commit hash.
        version : str
            Optional version label (e.g. ``"main"``, ``"1.0"``).
            Defaults to ``"latest"``.

        Returns
        -------
        Path
            The destination path where the artifact was stored.
        """
        dest_dir = self._builds_dir / commit_hash[:8] / version
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / source.name
        shutil.copy2(str(source), str(dest))
        logger.info("Stored artifact %s -> %s", source, dest)
        return dest

    def get(self, commit_hash: str, version: str = "latest") -> Path | None:
        """Get a previously stored artifact, or ``None`` if not found.

        Parameters
        ----------
        commit_hash : str
            40-character hexadecimal commit hash.
        version : str
            Optional version label.  Defaults to ``"latest"``.

        Returns
        -------
        Path | None
            Path to the artifact if it exists, otherwise ``None``.
        """
        dest = self._builds_dir / commit_hash[:8] / version
        if dest.exists():
            logger.debug("Found artifact at %s", dest)
            return dest
        logger.debug("No artifact found at %s", dest)
        return None
