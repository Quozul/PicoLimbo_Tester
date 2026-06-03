"""Unit tests for src/infrastructure/git_repository.py.

All tests use mocked subprocess.run — no real git operations.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure import git_repository


# ---------------------------------------------------------------------------
# Patch target — must patch where subprocess is imported, not at module level
# ---------------------------------------------------------------------------

_PATCH_TARGET = "src.infrastructure.git_repository.subprocess.run"


# ---------------------------------------------------------------------------
# 1. clone
# ---------------------------------------------------------------------------


class TestClone:
    def test_clone_calls_git_clone(self):
        """clone() should invoke git clone with the correct URL."""
        with patch(_PATCH_TARGET) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            repo = git_repository.GitRepository(
                repos_dir=Path("/tmp/repos"), timeout=60.0
            )
            repo.clone("Quozul", "PicoLimbo")
            mock_run.assert_called_once_with(
                ["git", "clone", "--depth", "1", "https://github.com/Quozul/PicoLimbo.git", "/tmp/repos/Quozul/PicoLimbo"],
                cwd=None,
                capture_output=True,
                text=True,
                timeout=60.0,
            )

    def test_clone_returns_existing_if_already_cloned(self):
        """clone() should skip git call when repo already exists."""
        with patch(_PATCH_TARGET) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            repo = git_repository.GitRepository(
                repos_dir=Path("/tmp/repos"), timeout=60.0
            )
            mock_run.reset_mock()
            # Simulate existing repo by patching Path.exists
            with patch.object(Path, "exists", return_value=True):
                with patch("pathlib.Path.mkdir"):
                    result = repo.clone("Quozul", "PicoLimbo")
                    assert result == Path("/tmp/repos/Quozul/PicoLimbo")
                    mock_run.assert_not_called()

    def test_clone_creates_parent_directories(self):
        """clone() should create parent directories before cloning."""
        with patch(_PATCH_TARGET) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with patch("pathlib.Path.mkdir") as mock_mkdir:
                repo = git_repository.GitRepository(
                    repos_dir=Path("/tmp/deep/repos"), timeout=60.0
                )
                repo.clone("Quozul", "PicoLimbo")
                mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_clone_returns_correct_path_structure(self):
        """clone() should return the expected path."""
        with patch(_PATCH_TARGET) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            repo = git_repository.GitRepository(
                repos_dir=Path("/tmp/repos"), timeout=60.0
            )
            result = repo.clone("Quozul", "PicoLimbo")
            assert result == Path("/tmp/repos/Quozul/PicoLimbo")


# ---------------------------------------------------------------------------
# 2. update
# ---------------------------------------------------------------------------


class TestUpdate:
    def test_update_runs_fetch_and_checkout(self):
        """update() should run git fetch then git checkout FETCH_HEAD."""
        with patch(_PATCH_TARGET) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            repo = git_repository.GitRepository(
                repos_dir=Path("/tmp/repos"), timeout=60.0
            )
            repo_path = Path("/tmp/repos/Quozul/PicoLimbo")
            repo.update(repo_path, "main")
            assert mock_run.call_count == 2
            # First call: git fetch
            fetch_call = mock_run.call_args_list[0]
            assert fetch_call[0][0] == ["git", "fetch", "--depth=1", "origin", "main"]
            assert fetch_call[1]["cwd"] == str(repo_path)
            # Second call: git checkout FETCH_HEAD
            checkout_call = mock_run.call_args_list[1]
            assert checkout_call[0][0] == ["git", "checkout", "FETCH_HEAD"]
            assert checkout_call[1]["cwd"] == str(repo_path)


# ---------------------------------------------------------------------------
# 3. resolve
# ---------------------------------------------------------------------------


class TestResolve:
    def test_resolve_commit_hash_directly(self):
        """resolve() should checkout and return the hash directly when ref is a commit hash."""
        with patch(_PATCH_TARGET) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            repo = git_repository.GitRepository(
                repos_dir=Path("/tmp/repos"), timeout=60.0
            )
            repo_path = Path("/tmp/repos/Quozul/PicoLimbo")
            commit_hash = "a" * 40
            result = repo.resolve(repo_path, commit_hash)
            assert result == commit_hash
            # Should only call git checkout (not fetch)
            mock_run.assert_called_once()
            assert mock_run.call_args[0][0] == ["git", "checkout", commit_hash]

    def test_resolve_branch_fetches_and_resolves(self):
        """resolve() should fetch and checkout branch, then rev-parse."""
        with patch(_PATCH_TARGET) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abcdef1234567890abcdef1234567890abcdef12", stderr="")
            repo = git_repository.GitRepository(
                repos_dir=Path("/tmp/repos"), timeout=60.0
            )
            repo_path = Path("/tmp/repos/Quozul/PicoLimbo")
            result = repo.resolve(repo_path, "main")
            assert result == "abcdef1234567890abcdef1234567890abcdef12"
            # Should call fetch, checkout FETCH_HEAD, and rev-parse
            assert mock_run.call_count == 3

    def test_resolve_branch_fallback_on_fetch_failure(self):
        """resolve() should fall back to rev-parse HEAD when fetch fails."""
        # Use a callable that tracks how many times it has been called
        call_order = []

        def mock_run_side_effect(*args, **kwargs):
            call_order.append(args[0])
            cmd = args[0]
            if cmd[1] in ("fetch", "checkout") and "FETCH_HEAD" not in cmd:
                # git fetch or git checkout (not FETCH_HEAD) — fail
                raise RuntimeError("Command failed")
            # git checkout FETCH_HEAD or git rev-parse — succeed
            if "FETCH_HEAD" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            # git rev-parse HEAD
            return MagicMock(returncode=0, stdout="fedcba0987654321fedcba0987654321fedcba09", stderr="")

        with patch(_PATCH_TARGET, side_effect=mock_run_side_effect) as mock_run:
            repo = git_repository.GitRepository(
                repos_dir=Path("/tmp/repos"), timeout=60.0
            )
            repo_path = Path("/tmp/repos/Quozul/PicoLimbo")
            result = repo.resolve(repo_path, "develop")
            assert result == "fedcba0987654321fedcba0987654321fedcba09"
            # git fetch fails, so checkout FETCH_HEAD is skipped,
            # then rev-parse HEAD succeeds — 2 calls total
            assert mock_run.call_count == 2


# ---------------------------------------------------------------------------
# 4. _run_git error handling
# ---------------------------------------------------------------------------


class TestRunGit:
    def test_raises_runtime_error_on_failure(self):
        """_run_git() should raise RuntimeError on non-zero exit code."""
        with patch(_PATCH_TARGET) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository",
            )
            repo = git_repository.GitRepository(
                repos_dir=Path("/tmp/repos"), timeout=60.0
            )
            with pytest.raises(RuntimeError, match="Command failed"):
                repo._run_git(["git", "status"], cwd=Path("/tmp"))

    def test_returns_stripped_stdout(self):
        """_run_git() should return stripped stdout."""
        with patch(_PATCH_TARGET) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="  abc123  \n",
                stderr="",
            )
            repo = git_repository.GitRepository(
                repos_dir=Path("/tmp/repos"), timeout=60.0
            )
            result = repo._run_git(["git", "rev-parse", "HEAD"])
            assert result == "abc123"

    def test_passes_timeout_correctly(self):
        """_run_git() should pass the configured timeout."""
        with patch(_PATCH_TARGET) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            repo = git_repository.GitRepository(
                repos_dir=Path("/tmp/repos"), timeout=300.0
            )
            repo._run_git(["git", "status"])
            assert mock_run.call_args[1]["timeout"] == 300.0


# ---------------------------------------------------------------------------
# 5. _is_commit_hash helper
# ---------------------------------------------------------------------------


class TestIsCommitHash:
    def test_valid_40_char_hex_lowercase(self):
        assert git_repository._is_commit_hash("a" * 40) is True

    def test_valid_40_char_hex_uppercase(self):
        assert git_repository._is_commit_hash("A" * 40) is True

    def test_valid_40_char_hex_mixed_case(self):
        # Exactly 40 hex chars with mixed case
        assert git_repository._is_commit_hash("aB3dEf456789012345678901234567890abcdef1") is True

    def test_invalid_short_hash(self):
        assert git_repository._is_commit_hash("abc1234") is False

    def test_invalid_branch_name(self):
        assert git_repository._is_commit_hash("main") is False

    def test_invalid_empty_string(self):
        assert git_repository._is_commit_hash("") is False

    def test_invalid_non_hex_characters(self):
        assert git_repository._is_commit_hash("g" * 40) is False

    def test_invalid_39_chars(self):
        assert git_repository._is_commit_hash("a" * 39) is False

    def test_invalid_41_chars(self):
        assert git_repository._is_commit_hash("a" * 41) is False
