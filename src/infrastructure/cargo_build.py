"""Cargo build adapter — encapsulates cargo build commands.

Provides a clean ``CargoBuildAdapter`` class that wraps cargo build
operations behind a simple interface.  All subprocess calls are isolated
here so the rest of the codebase never invokes ``subprocess`` directly
for cargo.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class CargoBuildAdapter:
    """Encapsulates cargo build operations.

    Parameters
    ----------
    timeout : float
        Maximum seconds allowed for the cargo build subprocess call.
        Defaults to 1800 (30 minutes).
    release : bool
        Whether to build with ``--release`` flags.  Defaults to ``True``.
    """

    def __init__(self, timeout: float = 1800.0, release: bool = True) -> None:
        self._timeout = timeout
        self._release = release

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, repo_path: Path) -> Path:
        """Build the Rust project with cargo.

        Runs ``cargo build`` (optionally with ``--release``) in the given
        repository directory and verifies that the expected binary was
        produced.

        Parameters
        ----------
        repo_path : Path
            Path to the Rust project root (where ``Cargo.toml`` lives).

        Returns
        -------
        Path
            Path to the built binary.

        Raises
        ------
        FileNotFoundError
            If the expected build artifact does not exist after the build.
        RuntimeError
            If the cargo build command exits with a non-zero return code.
        """
        flags = ["build", "--release"] if self._release else ["build"]
        logger.info("Running cargo %s (timeout=%ss, cwd=%s)", flags, self._timeout, repo_path)
        result = subprocess.run(
            ["cargo"] + flags,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"cargo build failed (exit {result.returncode}): "
                f"{' '.join(['cargo'] + flags)}\n"
                f"stderr: {result.stderr.strip()}"
            )

        # Verify artifact exists
        source = repo_path / "target" / "release" / "pico_limbo"
        if not source.exists():
            raise FileNotFoundError(
                f"Build artifact not found at {source}. "
                f"Cargo build may have failed silently."
            )
        logger.info("Build artifact found at %s", source)
        return source
