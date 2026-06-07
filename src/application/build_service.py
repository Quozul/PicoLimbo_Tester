"""Build service — domain service for building projects.

Orchestrates git clone/update, commit resolution, cargo build, and artifact
storage behind a single ``build()`` method.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from src.domain.value_objects import CommitHash, ArtifactPath
from src.infrastructure.artifact_storage import ArtifactStorage
from src.infrastructure.cargo_build import CargoBuildAdapter
from src.infrastructure.git_repository import GitRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuildResult:
    """Result of a build operation."""

    commit_hash: CommitHash
    artifact_path: ArtifactPath


class BuildService:
    """Domain service for building projects.

    Uses :class:`GitRepository`, :class:`CargoBuildAdapter`, and
    :class:`ArtifactStorage` to:

    1. Clone/update repository
    2. Resolve commit hash
    3. Build with cargo
    4. Store artifact

    Parameters
    ----------
    git_repo : GitRepository
        Git repository adapter.
    cargo : CargoBuildAdapter
        Cargo build adapter.
    artifact_storage : ArtifactStorage
        Artifact storage repository.
    builds_dir : Path
        Base directory for build artifacts (passed through to storage).
    """

    def __init__(
        self,
        git_repo: GitRepository,
        cargo: CargoBuildAdapter,
        artifact_storage: ArtifactStorage,
        builds_dir: Path,
    ) -> None:
        self._git = git_repo
        self._cargo = cargo
        self._storage = artifact_storage
        self._builds_dir = builds_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        repo_url: str,
        ref: str,
        owner: str,
        repo_name: str,
    ) -> BuildResult:
        """Build a project from a repository.

        Parameters
        ----------
        repo_url : str
            GitHub repository URL (e.g. ``"https://github.com/Quozul/PicoLimbo.git"``).
        ref : str
            Branch name or commit hash.
        owner : str
            Repository owner / organisation name.
        repo_name : str
            Repository name (without ``.git`` suffix).

        Returns
        -------
        BuildResult
            Contains the resolved commit hash and the artifact path.

        Raises
        ------
        RuntimeError
            If git clone, cargo build, or artifact storage fails.
        """
        # Git: clone or update
        repo_path = self._git.clone(owner, repo_name)

        # Git: resolve commit (also checks out the ref)
        raw_hash = self._git.resolve(repo_path, ref)
        commit_hash = CommitHash(raw_hash)

        # Check for cached artifact
        cached = self._storage.get(commit_hash.value)
        if cached is not None:
            logger.info("Build cache hit for %s, using cached artifact", commit_hash.value)
            return BuildResult(
                commit_hash=commit_hash,
                artifact_path=ArtifactPath(cached),
            )

        # Build
        source = self._cargo.build(repo_path)

        # Store artifact
        artifact_path = self._storage.store(source, commit_hash.value)

        return BuildResult(
            commit_hash=commit_hash,
            artifact_path=ArtifactPath(artifact_path),
        )
