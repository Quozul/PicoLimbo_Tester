"""Unit tests for src/builder/engine.py"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.builder import engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_path_mock(spec=Path):
    """Create a MagicMock that behaves like a Path for /-chaining.

    Every __truediv__ call returns the same mock, so
    mock / "a" / "b" / "c" is always the same object.
    """
    m = MagicMock(spec=spec)
    m.__truediv__ = MagicMock(return_value=m)
    return m


# ---------------------------------------------------------------------------
# 1. extract_owner_from_url
# ---------------------------------------------------------------------------

class TestExtractOwnerFromUrl:
    def test_full_url_with_git_suffix(self):
        owner, repo = engine.extract_owner_from_url(
            "https://github.com/Quozul/PicoLimbo.git"
        )
        assert owner == "Quozul"
        assert repo == "PicoLimbo"

    def test_full_url_without_git_suffix(self):
        owner, repo = engine.extract_owner_from_url(
            "https://github.com/Quozul/PicoLimbo"
        )
        assert owner == "Quozul"
        assert repo == "PicoLimbo"

    def test_repo_name_with_hyphens(self):
        owner, repo = engine.extract_owner_from_url(
            "https://github.com/owner/repo-name.git"
        )
        assert owner == "owner"
        assert repo == "repo-name"

    def test_three_path_segments_raises_value_error(self):
        with pytest.raises(ValueError, match="Only GitHub repository URLs"):
            engine.extract_owner_from_url("https://github.com/org/suborg/repo")

    def test_non_github_domain_raises_value_error(self):
        with pytest.raises(ValueError, match="Only GitHub repository URLs"):
            engine.extract_owner_from_url("https://gitlab.com/owner/repo")

    def test_no_repo_name_raises_value_error(self):
        with pytest.raises(ValueError, match="Only GitHub repository URLs"):
            engine.extract_owner_from_url("https://github.com/owner/")

    def test_not_a_url_raises_value_error(self):
        with pytest.raises(ValueError, match="Only GitHub repository URLs"):
            engine.extract_owner_from_url("not-a-url")


# ---------------------------------------------------------------------------
# 2. is_commit_hash
# ---------------------------------------------------------------------------

class TestIsCommitHash:
    def test_valid_40_char_lower_hex(self):
        assert engine.is_commit_hash(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ) is True

    def test_valid_40_char_all_zeros(self):
        assert engine.is_commit_hash(
            "0000000000000000000000000000000000000000"
        ) is True

    def test_valid_40_char_lowercase_hex(self):
        assert engine.is_commit_hash(
            "abcdef0123456789abcdef0123456789abcdef01"
        ) is True

    def test_valid_40_char_uppercase_hex(self):
        assert engine.is_commit_hash(
            "AABBCCDD00112233AABBCCDD00112233AABBCCDD"
        ) is True

    def test_valid_40_char_mixed_case_hex(self):
        assert engine.is_commit_hash(
            "AaBbCcDd00112233AaBbCcDd00112233AaBbCcDd"
        ) is True

    def test_branch_name_returns_false(self):
        assert engine.is_commit_hash("master") is False

    def test_short_hash_returns_false(self):
        assert engine.is_commit_hash("abc1234") is False

    def test_non_hex_chars_returns_false(self):
        assert engine.is_commit_hash(
            "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG"
        ) is False

    def test_39_chars_returns_false(self):
        assert engine.is_commit_hash(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ) is False

    def test_41_chars_returns_false(self):
        assert engine.is_commit_hash(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ) is False

    def test_empty_string_returns_false(self):
        assert engine.is_commit_hash("") is False


# ---------------------------------------------------------------------------
# 3. _get_git_repo  (lazy initialisation)
# ---------------------------------------------------------------------------

class TestGetGitRepo:
    def test_creates_git_repo_on_first_call(self):
        # Reset the module-level instance so we can test fresh creation
        engine._git_repo = None

        with patch(
            "src.builder.engine.git_repo_module.GitRepository"
        ) as mock_cls:
            instance = MagicMock()
            mock_cls.return_value = instance
            result = engine._get_git_repo()

        assert result is instance
        mock_cls.assert_called_once()
        assert mock_cls.call_args.kwargs["repos_dir"] is not None

    def test_returns_same_instance_on_subsequent_calls(self):
        mock_instance = MagicMock()
        engine._git_repo = mock_instance
        result = engine._get_git_repo()
        assert result is mock_instance


class TestGetCargo:
    def test_creates_cargo_adapter_on_first_call(self):
        # Reset the module-level instance so we can test fresh creation
        engine._cargo = None

        with patch(
            "src.builder.engine.cargo_build_module.CargoBuildAdapter"
        ) as mock_cls:
            instance = MagicMock()
            mock_cls.return_value = instance
            result = engine._get_cargo()

        assert result is instance
        mock_cls.assert_called_once()
        assert mock_cls.call_args.kwargs["timeout"] is not None

    def test_returns_same_instance_on_subsequent_calls(self):
        mock_instance = MagicMock()
        engine._cargo = mock_instance
        result = engine._get_cargo()
        assert result is mock_instance


# ---------------------------------------------------------------------------
# 4. build_project (now delegates to BuildService)
# ---------------------------------------------------------------------------

class TestBuildProject:
    def test_delegates_to_build_service(self):
        """build_project should delegate to BuildService.build()."""
        from src.application.build_service import BuildResult
        from src.domain.value_objects import ArtifactPath, CommitHash

        # Reset module-level service so we get a fresh one
        engine._build_service = None

        mock_service = MagicMock()
        mock_result = BuildResult(
            commit_hash=CommitHash("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
            artifact_path=ArtifactPath(Path("/app/builds/aaaaaaa1/latest/pico_limbo")),
        )
        mock_service.build.return_value = mock_result

        with patch.object(engine, "_get_build_service", return_value=mock_service):
            result = engine.build_project(
                "https://github.com/Quozul/PicoLimbo.git",
                "main",
                "Quozul",
                "PicoLimbo",
            )

        mock_service.build.assert_called_once_with(
            "https://github.com/Quozul/PicoLimbo.git", "main", "Quozul", "PicoLimbo"
        )
        assert isinstance(result, BuildResult)
        assert result.artifact_path.value == Path("/app/builds/aaaaaaa1/latest/pico_limbo")

    def test_returns_build_result_with_commit_hash_and_artifact_path(self):
        """build_project should return a BuildResult with correct values."""
        from src.application.build_service import BuildResult
        from src.domain.value_objects import ArtifactPath, CommitHash

        engine._build_service = None

        mock_service = MagicMock()
        mock_result = BuildResult(
            commit_hash=CommitHash("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"),
            artifact_path=ArtifactPath(Path("/app/builds/bbbbbbbb/latest/pico_limbo")),
        )
        mock_service.build.return_value = mock_result

        with patch.object(engine, "_get_build_service", return_value=mock_service):
            result = engine.build_project(
                "https://github.com/Quozul/PicoLimbo.git", "main", "Quozul", "PicoLimbo",
            )

        assert result.commit_hash.value == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        assert result.artifact_path.value.exists() is False  # mock path

    def test_raises_when_build_service_raises(self):
        """build_project should propagate exceptions from BuildService."""
        engine._build_service = None

        mock_service = MagicMock()
        mock_service.build.side_effect = RuntimeError("Build failed")

        with patch.object(engine, "_get_build_service", return_value=mock_service):
            with pytest.raises(RuntimeError, match="Build failed"):
                engine.build_project(
                    "https://github.com/Quozul/PicoLimbo.git", "main", "Quozul", "PicoLimbo",
                )

        mock_service.build.assert_called_once()


# ---------------------------------------------------------------------------
# 5. get_artifact_file
# ---------------------------------------------------------------------------

class TestGetArtifactFile:
    def test_returns_none_when_job_not_found(self):
        with patch.object(engine.database, "get_job_by_id", return_value=None):
            result = engine.get_artifact_file("job123")

        assert result is None

    def test_returns_none_when_job_has_no_artifact_path(self):
        with patch.object(engine.database, "get_job_by_id", return_value={
            "job_id": "job123",
            "artifact_path": None,
        }):
            result = engine.get_artifact_file("job123")

        assert result is None

    def test_returns_none_when_artifact_path_empty_string(self):
        with patch.object(engine.database, "get_job_by_id", return_value={
            "job_id": "job123",
            "artifact_path": "",
        }):
            result = engine.get_artifact_file("job123")

        assert result is None

    def test_returns_path_when_artifact_path_set(self):
        job = {
            "job_id": "job123",
            "artifact_path": "/app/builds/owner/main/abc123/pico_limbo",
        }
        with patch.object(engine.database, "get_job_by_id", return_value=job):
            result = engine.get_artifact_file("job123")

        assert isinstance(result, Path)
        assert str(result) == "/app/builds/owner/main/abc123/pico_limbo"


# ---------------------------------------------------------------------------
# 6. create_job
# ---------------------------------------------------------------------------

class TestCreateJob:
    def test_creates_job_with_all_steps(self):
        repo_url = "https://github.com/Quozul/PicoLimbo.git"
        ref = "main"
        versions = ["3.10", "3.11"]

        mock_repo_path = MagicMock(spec=Path)
        mock_job = {"job_id": "abc123", "status": "queued"}
        mock_git_repo = MagicMock()

        with patch.object(engine, "extract_owner_from_url", return_value=("Quozul", "PicoLimbo")) as mock_extract:
            with patch.object(engine, "_get_git_repo", return_value=mock_git_repo) as mock_get_git:
                mock_git_repo.clone.return_value = mock_repo_path
                mock_git_repo.resolve.return_value = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                with patch.object(engine.database, "create_job", return_value=mock_job) as mock_db_create:
                    result = engine.create_job(repo_url, ref, versions)

        assert result == mock_job
        mock_extract.assert_called_once_with(repo_url)
        mock_get_git.assert_called()
        mock_git_repo.clone.assert_called_once_with("Quozul", "PicoLimbo")
        mock_git_repo.resolve.assert_called_once_with(mock_repo_path, ref)
        mock_db_create.assert_called_once_with(
            repo_url, ref, "Quozul",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", versions,
            "none", "modern", None, None, 30,
        )

    def test_creates_job_with_empty_versions_when_none(self):
        repo_url = "https://github.com/Quozul/PicoLimbo.git"
        ref = "develop"

        mock_repo_path = MagicMock(spec=Path)
        mock_job = {"job_id": "def456", "status": "queued"}
        mock_git_repo = MagicMock()

        with patch.object(engine, "extract_owner_from_url", return_value=("Quozul", "PicoLimbo")) as mock_extract:
            with patch.object(engine, "_get_git_repo", return_value=mock_git_repo) as mock_get_git:
                mock_git_repo.clone.return_value = mock_repo_path
                mock_git_repo.resolve.return_value = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                with patch.object(engine.database, "create_job", return_value=mock_job) as mock_db_create:
                    result = engine.create_job(repo_url, ref, None)

        assert result == mock_job
        mock_extract.assert_called_once_with(repo_url)
        mock_get_git.assert_called()
        mock_git_repo.clone.assert_called_once_with("Quozul", "PicoLimbo")
        mock_git_repo.resolve.assert_called_once_with(mock_repo_path, ref)
        mock_db_create.assert_called_once_with(
            repo_url, ref, "Quozul",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", [],
            "none", "modern", None, None, 30,
        )

    def test_creates_job_with_versions_list(self):
        repo_url = "https://github.com/Quozul/PicoLimbo.git"
        ref = "main"
        versions = ["3.10"]

        mock_repo_path = MagicMock(spec=Path)
        mock_job = {"job_id": "ghi789", "status": "queued"}
        mock_git_repo = MagicMock()

        with patch.object(engine, "extract_owner_from_url", return_value=("Quozul", "PicoLimbo")) as mock_extract:
            with patch.object(engine, "_get_git_repo", return_value=mock_git_repo) as mock_get_git:
                mock_git_repo.clone.return_value = mock_repo_path
                mock_git_repo.resolve.return_value = "cccccccccccccccccccccccccccccccccccccccc"
                with patch.object(engine.database, "create_job", return_value=mock_job) as mock_db_create:
                    result = engine.create_job(repo_url, ref, versions)

        assert result == mock_job
        mock_extract.assert_called_once_with(repo_url)
        mock_get_git.assert_called()
        mock_git_repo.clone.assert_called_once_with("Quozul", "PicoLimbo")
        mock_git_repo.resolve.assert_called_once_with(mock_repo_path, ref)
        mock_db_create.assert_called_once_with(
            repo_url, ref, "Quozul",
            "cccccccccccccccccccccccccccccccccccccccc", versions,
            "none", "modern", None, None, 30,
        )
