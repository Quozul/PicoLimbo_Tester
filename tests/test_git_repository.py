"""Integration tests for src/infrastructure/git_repository.py.

These tests use real git operations against a temporary directory
to verify clone, update, and resolve behaviour.
"""

import subprocess
from pathlib import Path

import pytest

from src.infrastructure import git_repository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def git(tmp_path: Path) -> git_repository.GitRepository:
    """Return a GitRepository backed by a temporary directory."""
    return git_repository.GitRepository(repos_dir=tmp_path, timeout=60.0)


# ---------------------------------------------------------------------------
# 1. clone
# ---------------------------------------------------------------------------

class TestClone:
    def test_clone_clones_repo(self, git: git_repository.GitRepository):
        path = git.clone("Quozul", "PicoLimbo")
        assert (path / ".git").exists()

    def test_clone_returns_existing_if_already_cloned(self, git: git_repository.GitRepository):
        path1 = git.clone("Quozul", "PicoLimbo")
        path2 = git.clone("Quozul", "PicoLimbo")
        assert path1 == path2

    def test_clone_creates_parent_directories(self, tmp_path: Path):
        """Deep nested paths should have parents created automatically."""
        git = git_repository.GitRepository(repos_dir=tmp_path, timeout=60.0)
        path = git.clone("Quozul", "PicoLimbo")
        assert path.exists()
        assert (path / ".git").exists()

    def test_clone_returns_correct_path_structure(self, git: git_repository.GitRepository):
        path = git.clone("Quozul", "PicoLimbo")
        assert str(path) == str(git._repos_dir / "Quozul" / "PicoLimbo")


# ---------------------------------------------------------------------------
# 2. update
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_update_fetches_and_checkouts(self, git: git_repository.GitRepository):
        git.clone("Quozul", "PicoLimbo")
        repo_path = git._repos_dir / "Quozul" / "PicoLimbo"
        git.update(repo_path, "master")
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert len(result.stdout.strip()) == 40


# ---------------------------------------------------------------------------
# 3. resolve
# ---------------------------------------------------------------------------

class TestResolve:
    def test_resolve_commit_returns_hash(self, git: git_repository.GitRepository):
        git.clone("Quozul", "PicoLimbo")
        repo_path = git._repos_dir / "Quozul" / "PicoLimbo"
        hash_result = git.resolve(repo_path, "master")
        assert len(hash_result.strip()) == 40

    def test_resolve_commit_hash_directly(self, git: git_repository.GitRepository):
        git.clone("Quozul", "PicoLimbo")
        repo_path = git._repos_dir / "Quozul" / "PicoLimbo"
        # Get a real commit hash first
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        commit_hash = result.stdout.strip()
        # Resolve the same hash directly
        resolved = git.resolve(repo_path, commit_hash)
        assert resolved == commit_hash

    def test_resolve_branch_fetches_and_resolves(self, git: git_repository.GitRepository):
        git.clone("Quozul", "PicoLimbo")
        repo_path = git._repos_dir / "Quozul" / "PicoLimbo"
        hash_result = git.resolve(repo_path, "master")
        assert len(hash_result.strip()) == 40


# ---------------------------------------------------------------------------
# 4. _run_git error handling
# ---------------------------------------------------------------------------

class TestRunGit:
    def test_raises_runtime_error_on_failure(self, git: git_repository.GitRepository):
        with pytest.raises(RuntimeError, match="Command failed"):
            # Use /tmp (exists but not a git repo) so git runs but fails
            git._run_git(["git", "status"], cwd=Path("/tmp"))

    def test_returns_stripped_stdout(self, git: git_repository.GitRepository):
        git.clone("Quozul", "PicoLimbo")
        repo_path = git._repos_dir / "Quozul" / "PicoLimbo"
        result = git._run_git(["git", "rev-parse", "HEAD"], cwd=repo_path)
        assert result == result.strip()
        assert len(result) == 40


# ---------------------------------------------------------------------------
# 5. _is_commit_hash helper
# ---------------------------------------------------------------------------

class TestIsCommitHash:
    def test_valid_40_char_hex(self):
        assert git_repository._is_commit_hash(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ) is True

    def test_invalid_short_hash(self):
        assert git_repository._is_commit_hash("abc1234") is False

    def test_invalid_branch_name(self):
        assert git_repository._is_commit_hash("main") is False

    def test_empty_string(self):
        assert git_repository._is_commit_hash("") is False
