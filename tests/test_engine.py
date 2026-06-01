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


# ---------------------------------------------------------------------------
# 4. build_project
# ---------------------------------------------------------------------------

class TestBuildProject:
    def test_returns_existing_artifact_path(self):
        artifact_path = _make_path_mock()
        artifact_path.exists.return_value = True
        artifact_path.__str__ = lambda self: "/app/builds/owner/main/abc123/pico_limbo"

        artifact_dir = _make_path_mock()
        artifact_dir.__truediv__ = MagicMock(
            side_effect=lambda other: artifact_path if other == "pico_limbo" else artifact_dir
        )
        artifact_dir.__str__ = lambda self: "/app/builds/owner/main/abc123"

        with patch.object(engine, "BUILDS_DIR", artifact_dir):
            with patch.object(engine, "_get_git_repo") as mock_get_git:
                mock_git_repo = MagicMock()
                mock_get_git.return_value = mock_git_repo
                with patch("src.builder.engine.shutil.copy2") as mock_copy:
                    result = engine.build_project(
                        Path("/repos/owner/repo"),
                        "abc123",
                        "owner",
                        "main",
                    )

        assert result == "/app/builds/owner/main/abc123/pico_limbo"
        mock_git_repo._run_git.assert_not_called()
        mock_copy.assert_not_called()

    def test_builds_and_copies_when_artifact_missing(self):
        artifact_path = _make_path_mock()
        artifact_path.exists.return_value = False
        artifact_path.__str__ = lambda self: "/app/builds/owner/main/abc123/pico_limbo"

        source_path = _make_path_mock()
        source_path.exists.return_value = True
        source_path.__str__ = lambda self: "/repos/owner/repo/target/release/pico_limbo"

        artifact_dir = _make_path_mock()
        artifact_dir.__truediv__ = MagicMock(
            side_effect=lambda other: artifact_path if other == "pico_limbo" else artifact_dir
        )

        repo_mock = _make_path_mock()
        repo_mock.__truediv__ = MagicMock(
            side_effect=lambda other: source_path if other == "target" else repo_mock
        )
        source_path.__truediv__ = MagicMock(
            side_effect=lambda other: source_path if other == "release" else source_path
        )

        repo_path = Path("/repos/owner/repo")

        with patch.object(Path, "exists") as mock_path_exists:
            mock_path_exists.return_value = True

            with patch.object(engine, "BUILDS_DIR", artifact_dir):
                with patch.object(engine, "_get_git_repo") as mock_get_git:
                    mock_git_repo = MagicMock()
                    mock_get_git.return_value = mock_git_repo
                    with patch("src.builder.engine.shutil.copy2") as mock_copy:
                        result = engine.build_project(
                            repo_path,
                            "abc123",
                            "owner",
                            "main",
                        )

        assert result == "/app/builds/owner/main/abc123/pico_limbo"
        mock_git_repo._run_git.assert_called_once_with(
            ["cargo", "build", "--release"],
            cwd=repo_path,
        )
        mock_copy.assert_called_once_with(
            "/repos/owner/repo/target/release/pico_limbo",
            "/app/builds/owner/main/abc123/pico_limbo",
        )

    def test_raises_file_not_found_when_cargo_does_not_produce_artifact(self):
        artifact_path = _make_path_mock()
        artifact_path.exists.return_value = False
        artifact_path.__str__ = lambda self: "/app/builds/owner/main/abc123/pico_limbo"

        artifact_dir = _make_path_mock()
        artifact_dir.__truediv__ = MagicMock(
            side_effect=lambda other: artifact_path if other == "pico_limbo" else artifact_dir
        )

        source_path = _make_path_mock()
        source_path.exists.return_value = False
        source_path.__str__ = lambda self: "/repos/owner/repo/target/release/pico_limbo"

        repo_mock = _make_path_mock()
        repo_mock.__truediv__ = MagicMock(
            side_effect=lambda other: source_path if other == "target" else repo_mock
        )
        source_path.__truediv__ = MagicMock(
            side_effect=lambda other: source_path if other == "release" else source_path
        )

        repo_path = Path("/repos/owner/repo")

        with patch.object(engine, "BUILDS_DIR", artifact_dir):
            with patch.object(engine, "_get_git_repo") as mock_get_git:
                mock_git_repo = MagicMock()
                mock_get_git.return_value = mock_git_repo
                with patch("src.builder.engine.shutil.copy2") as mock_copy:
                    with pytest.raises(FileNotFoundError) as exc_info:
                        engine.build_project(
                            repo_path,
                            "abc123",
                            "owner",
                            "main",
                        )

                    assert "Build artifact not found" in str(exc_info.value)
                    mock_copy.assert_not_called()


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
