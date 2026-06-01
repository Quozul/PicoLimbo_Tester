"""Tests for src/application/build_service.py"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.application.build_service import BuildResult, BuildService
from src.domain.value_objects import ArtifactPath, CommitHash
from src.infrastructure.artifact_storage import ArtifactStorage
from src.infrastructure.cargo_build import CargoBuildAdapter
from src.infrastructure.git_repository import GitRepository


# ---------------------------------------------------------------------------
# 1. BuildService — integration test with real git + cargo
# ---------------------------------------------------------------------------

class TestBuildServiceIntegration:
    """Integration tests that use real git clone and cargo build."""

    def test_build_clones_repo_resolves_commit_and_builds(self, tmp_path: Path) -> None:
        """Integration test: real git clone, real cargo build."""
        git = GitRepository(repos_dir=tmp_path / "repos")
        cargo = CargoBuildAdapter()
        storage = ArtifactStorage(tmp_path / "builds")

        service = BuildService(git, cargo, storage, tmp_path / "builds")
        result = service.build(
            repo_url="https://github.com/Quozul/PicoLimbo.git",
            ref="main",
            owner="Quozul",
            repo_name="PicoLimbo",
        )

        assert isinstance(result.commit_hash, CommitHash)
        assert len(result.commit_hash.value) == 40
        assert isinstance(result.artifact_path, ArtifactPath)
        assert result.artifact_path.value.exists()

    def test_build_caches_existing_repo(self, tmp_path: Path) -> None:
        """Building twice should reuse the existing cloned repo."""
        git = GitRepository(repos_dir=tmp_path / "repos")
        cargo = CargoBuildAdapter()
        storage = ArtifactStorage(tmp_path / "builds")

        service = BuildService(git, cargo, storage, tmp_path / "builds")
        result1 = service.build(
            "https://github.com/Quozul/PicoLimbo.git", "main", "Quozul", "PicoLimbo",
        )
        result2 = service.build(
            "https://github.com/Quozul/PicoLimbo.git", "main", "Quozul", "PicoLimbo",
        )

        # Both should produce the same commit hash
        assert result1.commit_hash.value == result2.commit_hash.value


# ---------------------------------------------------------------------------
# 2. BuildService — unit tests with mocked adapters
# ---------------------------------------------------------------------------

def _make_mock_git(
    repo_path: Path = Path("/tmp/repo"),
    commit_hash: str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
) -> GitRepository:
    """Create a mock GitRepository."""
    mock = MagicMock(spec=GitRepository)
    mock.clone.return_value = repo_path
    mock.resolve.return_value = commit_hash
    return mock


def _make_mock_cargo(
    build_path: Path = Path("/tmp/repo/target/release/pico_limbo"),
) -> CargoBuildAdapter:
    """Create a mock CargoBuildAdapter."""
    mock = MagicMock(spec=CargoBuildAdapter)
    mock.build.return_value = build_path
    return mock


def _make_mock_storage(
    stored_path: Path = Path("/app/builds/aaaaaaa1/latest/pico_limbo"),
) -> ArtifactStorage:
    """Create a mock ArtifactStorage."""
    mock = MagicMock(spec=ArtifactStorage)
    mock.store.return_value = stored_path
    return mock


class TestBuildServiceUnit:
    """Unit tests with injected mocks — no subprocess calls."""

    def test_build_calls_clone_resolve_build_and_store(self, tmp_path: Path) -> None:
        """Verify the full build pipeline is called in the right order."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        mock_git = _make_mock_git(repo_path=repo_path)
        mock_cargo = _make_mock_cargo(build_path=repo_path / "target" / "release" / "pico_limbo")
        mock_storage = _make_mock_storage()

        service = BuildService(mock_git, mock_cargo, mock_storage, tmp_path / "builds")
        result = service.build(
            "https://github.com/Quozul/PicoLimbo.git", "main", "Quozul", "PicoLimbo",
        )

        mock_git.clone.assert_called_once_with("Quozul", "PicoLimbo")
        mock_git.resolve.assert_called_once_with(repo_path, "main")
        mock_cargo.build.assert_called_once_with(repo_path)
        mock_storage.store.assert_called_once()

        assert isinstance(result.commit_hash, CommitHash)
        assert len(result.commit_hash.value) == 40
        assert isinstance(result.artifact_path, ArtifactPath)

    def test_build_result_contains_correct_values(self, tmp_path: Path) -> None:
        """BuildResult should contain the commit hash and artifact path."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        commit_hash = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        stored_path = tmp_path / "builds" / "bbbbbbbb" / "latest" / "pico_limbo"

        mock_git = _make_mock_git(repo_path=repo_path, commit_hash=commit_hash)
        mock_cargo = _make_mock_cargo(build_path=repo_path / "target" / "release" / "pico_limbo")
        mock_storage = _make_mock_storage(stored_path=stored_path)

        service = BuildService(mock_git, mock_cargo, mock_storage, tmp_path / "builds")
        result = service.build(
            "https://github.com/Quozul/PicoLimbo.git", "main", "Quozul", "PicoLimbo",
        )

        assert result.commit_hash.value == commit_hash
        assert result.artifact_path.value == stored_path

    def test_build_result_is_frozen(self, tmp_path: Path) -> None:
        """BuildResult should be immutable (frozen dataclass)."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        mock_git = _make_mock_git(repo_path=repo_path)
        mock_cargo = _make_mock_cargo(build_path=repo_path / "target" / "release" / "pico_limbo")
        mock_storage = _make_mock_storage()

        service = BuildService(mock_git, mock_cargo, mock_storage, tmp_path / "builds")
        result = service.build(
            "https://github.com/Quozul/PicoLimbo.git", "main", "Quozul", "PicoLimbo",
        )

        with pytest.raises(AttributeError):
            result.commit_hash = CommitHash("0000000000000000000000000000000000000000")


# ---------------------------------------------------------------------------
# 3. ArtifactStorage — unit tests
# ---------------------------------------------------------------------------

class TestArtifactStorage:
    """Tests for ArtifactStorage."""

    def test_store_creates_directory_and_copies_file(self, tmp_path: Path) -> None:
        """Store should create the directory structure and copy the file."""
        source = tmp_path / "source" / "pico_limbo"
        source.parent.mkdir(parents=True)
        source.write_text("binary content")

        storage = ArtifactStorage(tmp_path / "builds")
        result = storage.store(source, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

        expected = tmp_path / "builds" / "aaaaaaaa" / "latest" / "pico_limbo"
        assert result == expected
        assert result.exists()
        assert result.read_text() == "binary content"

    def test_store_with_custom_version(self, tmp_path: Path) -> None:
        """Store should use the custom version label in the path."""
        source = tmp_path / "source" / "pico_limbo"
        source.parent.mkdir(parents=True)
        source.write_text("binary content")

        storage = ArtifactStorage(tmp_path / "builds")
        result = storage.store(source, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", version="main")

        expected = tmp_path / "builds" / "bbbbbbbb" / "main" / "pico_limbo"
        assert result == expected

    def test_get_returns_path_when_artifact_exists(self, tmp_path: Path) -> None:
        """Get should return the path when the artifact is stored."""
        storage = ArtifactStorage(tmp_path / "builds")
        source = tmp_path / "source" / "pico_limbo"
        source.parent.mkdir(parents=True)
        source.write_text("binary content")

        storage.store(source, "cccccccccccccccccccccccccccccccccccccccc")
        result = storage.get("cccccccccccccccccccccccccccccccccccccccc")

        assert result is not None
        assert result.exists()

    def test_get_returns_none_for_missing_artifact(self, tmp_path: Path) -> None:
        """Storage should return None for non-existent artifacts."""
        storage = ArtifactStorage(tmp_path / "builds")
        assert storage.get("nonexistent") is None

    def test_get_with_custom_version(self, tmp_path: Path) -> None:
        """Get should respect the custom version label."""
        source = tmp_path / "source" / "pico_limbo"
        source.parent.mkdir(parents=True)
        source.write_text("binary content")

        storage = ArtifactStorage(tmp_path / "builds")
        storage.store(source, "dddddddddddddddddddddddddddddddddddddddd", version="develop")

        result = storage.get("dddddddddddddddddddddddddddddddddddddddd", version="develop")
        assert result is not None

        # Default version "latest" should not find it
        assert storage.get("dddddddddddddddddddddddddddddddddddddddd") is None
