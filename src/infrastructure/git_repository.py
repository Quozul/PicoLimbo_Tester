"""Git repository adapter — encapsulates all git operations.

Provides a clean ``GitRepository`` class that wraps git clone, update, and
commit-resolution operations behind a simple interface.  All subprocess calls
are isolated here so the rest of the codebase never invokes ``subprocess``
directly for git.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class GitRepository:
    """Encapsulates git clone, update, and commit-resolution operations.

    Parameters
    ----------
    repos_dir : Path
        Base directory where cloned repositories are stored.
    timeout : float
        Maximum seconds allowed for any single git subprocess call.
        Defaults to 1800 (30 minutes).
    """

    def __init__(self, repos_dir: Path, timeout: float = 1800.0) -> None:
        self._repos_dir = repos_dir
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clone(self, owner: str, repo_name: str) -> Path:
        """Clone a GitHub repository.

        If the repository already exists (directory present and ``.git``
        subdirectory present), returns the existing path without cloning.

        Parameters
        ----------
        owner : str
            GitHub owner / organisation name.
        repo_name : str
            Repository name (without ``.git`` suffix).

        Returns
        -------
        Path
            Absolute path to the cloned repository.

        Raises
        ------
        RuntimeError
            If the git clone command fails.
        """
        repo_path = self._repos_dir / owner / repo_name

        if repo_path.exists() and (repo_path / ".git").exists():
            logger.info("Repo already cloned at %s", repo_path)
            return repo_path

        repo_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://github.com/{owner}/{repo_name}.git"
        self._run_git(["git", "clone", "--depth", "1", url, str(repo_path)])
        logger.info("Cloned repo to %s", repo_path)
        return repo_path

    def update(self, repo_path: Path, ref: str) -> None:
        """Fetch the latest from *origin* and checkout *ref*.

        Parameters
        ----------
        repo_path : Path
            Path to the local repository.
        ref : str
            Branch name or tag to checkout (e.g. ``main``, ``develop``).

        Raises
        ------
        RuntimeError
            If the fetch or checkout command fails.
        """
        logger.info("Updating repo at %s (ref=%s)", repo_path, ref)
        self._run_git(["git", "fetch", "--depth=1", "origin", ref], cwd=repo_path)
        self._run_git(["git", "checkout", "FETCH_HEAD"], cwd=repo_path)
        logger.info("Repo updated at %s", repo_path)

    def resolve(self, repo_path: Path, ref: str) -> str:
        """Resolve a ref to a full 40-character commit hash.

        If *ref* is a commit hash, it is checked out directly.
        Otherwise the branch/tag is fetched and checked out, then resolved
        via ``git rev-parse HEAD``.

        Parameters
        ----------
        repo_path : Path
            Path to the local repository.
        ref : str
            Branch name, tag, or 40-character commit hash.

        Returns
        -------
        str
            Full 40-character hexadecimal commit hash.

        Raises
        ------
        RuntimeError
            If the git checkout or rev-parse command fails.
        """
        if _is_commit_hash(ref):
            self._run_git(["git", "checkout", ref], cwd=repo_path)
            logger.info("Checked out commit %s", ref)
            return ref
        # Fetch the specific branch/tag with depth=1 (shallow-clone friendly)
        self._run_git(["git", "fetch", "--depth=1", "origin", ref], cwd=repo_path)
        self._run_git(["git", "checkout", "FETCH_HEAD"], cwd=repo_path)
        output = self._run_git(["git", "rev-parse", "HEAD"], cwd=repo_path)
        commit_hash = output
        logger.info("Branch '%s' resolved to commit %s", ref, commit_hash)
        return commit_hash

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_git(self, args: list[str], cwd: Path | None = None) -> str:
        """Run a git command and return its stripped stdout.

        Parameters
        ----------
        args : list[str]
            Command arguments (e.g. ``["git", "status"]``).
        cwd : Path | None
            Working directory.  If ``None``, the current directory is used.

        Returns
        -------
        str
            Stripped stdout from the command.

        Raises
        ------
        RuntimeError
            If the command exits with a non-zero return code.
        """
        logger.info("Running: %s (cwd=%s)", " ".join(args), cwd)
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed (exit {result.returncode}): {' '.join(args)}\n"
                f"stderr: {result.stderr.strip()}"
            )
        return result.stdout.strip()


def _is_commit_hash(ref: str) -> bool:
    """Check if *ref* looks like a 40-character hexadecimal commit hash."""
    import re
    return bool(re.match(r"^[0-9a-fA-F]{40}$", ref))
