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
        # The source regex is [0-9a-f] (lowercase only).
        # This string is all lowercase hex, 40 chars.
        assert engine.is_commit_hash(
            "abcdef0123456789abcdef0123456789abcdef01"
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
# 3. _run
# ---------------------------------------------------------------------------

class TestRun:
    def test_returns_stripped_stdout_on_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  hello world  \n"
        mock_result.stderr = ""

        with patch("src.builder.engine.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            output = engine._run(["echo", "hello"], cwd=Path("/tmp"))

        assert output == "hello world"
        mock_run.assert_called_once_with(
            ["echo", "hello"],
            cwd="/tmp",
            capture_output=True,
            text=True,
            timeout=1800,
        )

    def test_raises_runtime_error_on_nonzero_returncode(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "fatal: not a git repository\n"

        with patch("src.builder.engine.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            with pytest.raises(RuntimeError) as exc_info:
                engine._run(["git", "status"], cwd=Path("/tmp"))

        assert "exit 1" in str(exc_info.value)
        assert "git status" in str(exc_info.value)
        assert "fatal: not a git repository" in str(exc_info.value)

    def test_stderr_stripped_in_error_message(self):
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        mock_result.stderr = "  error with whitespace  \n"

        with patch("src.builder.engine.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            with pytest.raises(RuntimeError) as exc_info:
                engine._run(["git", "bad-cmd"], cwd=Path("/tmp"))

        assert "error with whitespace" in str(exc_info.value)
        # stderr should be stripped (no leading/trailing whitespace)
        assert "  error" not in str(exc_info.value)

    def test_cwd_converted_to_string(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ok\n"
        mock_result.stderr = ""

        with patch("src.builder.engine.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            engine._run(["cmd"], cwd=Path("/some/path"))

        call_kwargs = mock_run.call_args
        assert call_kwargs[1]["cwd"] == "/some/path"


# ---------------------------------------------------------------------------
# 4. ensure_repo_cloned
# ---------------------------------------------------------------------------

class TestEnsureRepoCloned:
    def test_returns_existing_path_when_repo_and_git_exist(self):
        mock_repo_path = _make_path_mock()
        mock_repo_path.exists.return_value = True
        mock_git = _make_path_mock()
        mock_git.exists.return_value = True

        # repo_path / ".git" should return mock_git
        mock_repo_path.__truediv__ = MagicMock(
            side_effect=lambda other: mock_git if other == ".git" else mock_repo_path
        )

        mock_repos_dir = _make_path_mock()
        mock_repos_dir.__truediv__ = MagicMock(
            side_effect=lambda other: mock_repo_path if other == "owner" else mock_repos_dir
        )

        with patch.object(engine, "REPOS_DIR", mock_repos_dir):
            with patch.object(engine, "_run") as mock_run:
                result = engine.ensure_repo_cloned("owner", "repo")

        assert result == mock_repo_path
        mock_run.assert_not_called()

    def test_clones_when_repo_does_not_exist(self):
        mock_repo_path = _make_path_mock()
        mock_repo_path.exists.return_value = False
        mock_repo_path.__str__ = lambda self: "/repos/owner/repo"

        mock_repos_dir = _make_path_mock()
        mock_repos_dir.__truediv__ = MagicMock(
            side_effect=lambda other: mock_repo_path if other == "owner" else mock_repos_dir
        )

        with patch.object(engine, "REPOS_DIR", mock_repos_dir):
            with patch.object(engine, "_run") as mock_run:
                result = engine.ensure_repo_cloned("owner", "repo")

        assert result == mock_repo_path
        mock_repo_path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_run.assert_called_once_with(
            ["git", "clone", "--depth", "1",
             "https://github.com/owner/repo.git",
             "/repos/owner/repo"],
            cwd=Path.home(),
        )

    def test_clones_when_git_subdir_missing(self):
        mock_repo_path = _make_path_mock()
        mock_repo_path.exists.return_value = True
        mock_git = _make_path_mock()
        mock_git.exists.return_value = False
        mock_repo_path.__truediv__ = MagicMock(
            side_effect=lambda other: mock_git if other == ".git" else mock_repo_path
        )

        mock_repos_dir = _make_path_mock()
        mock_repos_dir.__truediv__ = MagicMock(
            side_effect=lambda other: mock_repo_path if other == "owner" else mock_repos_dir
        )

        with patch.object(engine, "REPOS_DIR", mock_repos_dir):
            with patch.object(engine, "_run") as mock_run:
                result = engine.ensure_repo_cloned("owner", "repo")

        assert result == mock_repo_path
        mock_repo_path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# 5. update_repo
# ---------------------------------------------------------------------------

class TestUpdateRepo:
    def test_fetches_and_checks_out_fetch_head(self):
        repo_path = Path("/repos/owner/repo")

        with patch.object(engine, "_run") as mock_run:
            engine.update_repo(repo_path, "main")

        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["git", "fetch", "--depth=1", "origin", "main"],
            cwd=repo_path,
        )
        mock_run.assert_any_call(
            ["git", "checkout", "FETCH_HEAD"],
            cwd=repo_path,
        )


# ---------------------------------------------------------------------------
# 6. resolve_commit
# ---------------------------------------------------------------------------

class TestResolveCommit:
    def test_commit_hash_direct_checkout(self):
        repo_path = Path("/repos/owner/repo")
        commit_hash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        with patch.object(engine, "_run") as mock_run:
            result = engine.resolve_commit(repo_path, commit_hash)

        assert result == commit_hash
        mock_run.assert_called_once_with(
            ["git", "checkout", commit_hash],
            cwd=repo_path,
        )

    def test_branch_fetch_checkout_and_rev_parse(self):
        repo_path = Path("/repos/owner/repo")
        branch = "develop"
        resolved_hash = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

        def side_effect(cmd, cwd):
            if "rev-parse" in cmd:
                return resolved_hash
            return ""

        with patch.object(engine, "_run", side_effect=side_effect) as mock_run:
            result = engine.resolve_commit(repo_path, branch)

        assert result == resolved_hash
        assert mock_run.call_count == 3
        mock_run.assert_any_call(
            ["git", "fetch", "--depth=1", "origin", "develop"],
            cwd=repo_path,
        )
        mock_run.assert_any_call(
            ["git", "checkout", "FETCH_HEAD"],
            cwd=repo_path,
        )
        mock_run.assert_any_call(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
        )


# ---------------------------------------------------------------------------
# 7. build_project
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
            with patch.object(engine, "_run") as mock_run:
                with patch("src.builder.engine.shutil.copy2") as mock_copy:
                    result = engine.build_project(
                        Path("/repos/owner/repo"),
                        "abc123",
                        "owner",
                        "main",
                    )

        assert result == "/app/builds/owner/main/abc123/pico_limbo"
        mock_run.assert_not_called()
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

        # repo_path / "target" / "release" / "pico_limbo" → source_path
        repo_mock = _make_path_mock()
        repo_mock.__truediv__ = MagicMock(
            side_effect=lambda other: source_path if other == "target" else repo_mock
        )
        source_path.__truediv__ = MagicMock(
            side_effect=lambda other: source_path if other == "release" else source_path
        )

        repo_path = Path("/repos/owner/repo")

        # Patch Path.exists so the source path (constructed via real Path /-chaining)
        # returns True for exists(). The source is repo_path / "target" / "release" / "pico_limbo"
        with patch.object(Path, "exists") as mock_path_exists:
            mock_path_exists.return_value = True

            with patch.object(engine, "BUILDS_DIR", artifact_dir):
                with patch.object(engine, "_run") as mock_run:
                    with patch("src.builder.engine.shutil.copy2") as mock_copy:
                        result = engine.build_project(
                            repo_path,
                            "abc123",
                            "owner",
                            "main",
                        )

        assert result == "/app/builds/owner/main/abc123/pico_limbo"
        mock_run.assert_called_once_with(
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

        # source_path for target/release/pico_limbo — exists returns False
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
            with patch.object(engine, "_run") as mock_run:
                mock_run.return_value = ""
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
# 8. get_artifact_file
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
# 9. create_job
# ---------------------------------------------------------------------------

class TestCreateJob:
    def test_creates_job_with_all_steps(self):
        repo_url = "https://github.com/Quozul/PicoLimbo.git"
        ref = "main"
        versions = ["3.10", "3.11"]

        mock_repo_path = MagicMock(spec=Path)
        mock_job = {"job_id": "abc123", "status": "queued"}

        with patch.object(engine, "extract_owner_from_url", return_value=("Quozul", "PicoLimbo")) as mock_extract:
            with patch.object(engine, "ensure_repo_cloned", return_value=mock_repo_path) as mock_clone:
                with patch.object(engine, "resolve_commit", return_value="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa") as mock_resolve:
                    with patch.object(engine.database, "create_job", return_value=mock_job) as mock_db_create:
                        result = engine.create_job(repo_url, ref, versions)

        assert result == mock_job
        mock_extract.assert_called_once_with(repo_url)
        mock_clone.assert_called_once_with("Quozul", "PicoLimbo")
        mock_resolve.assert_called_once_with(mock_repo_path, ref)
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

        with patch.object(engine, "extract_owner_from_url", return_value=("Quozul", "PicoLimbo")) as mock_extract:
            with patch.object(engine, "ensure_repo_cloned", return_value=mock_repo_path) as mock_clone:
                with patch.object(engine, "resolve_commit", return_value="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb") as mock_resolve:
                    with patch.object(engine.database, "create_job", return_value=mock_job) as mock_db_create:
                        result = engine.create_job(repo_url, ref, None)

        assert result == mock_job
        mock_extract.assert_called_once_with(repo_url)
        mock_clone.assert_called_once_with("Quozul", "PicoLimbo")
        mock_resolve.assert_called_once_with(mock_repo_path, ref)
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

        with patch.object(engine, "extract_owner_from_url", return_value=("Quozul", "PicoLimbo")) as mock_extract:
            with patch.object(engine, "ensure_repo_cloned", return_value=mock_repo_path) as mock_clone:
                with patch.object(engine, "resolve_commit", return_value="cccccccccccccccccccccccccccccccccccccccc") as mock_resolve:
                    with patch.object(engine.database, "create_job", return_value=mock_job) as mock_db_create:
                        result = engine.create_job(repo_url, ref, versions)

        assert result == mock_job
        mock_extract.assert_called_once_with(repo_url)
        mock_clone.assert_called_once_with("Quozul", "PicoLimbo")
        mock_resolve.assert_called_once_with(mock_repo_path, ref)
        mock_db_create.assert_called_once_with(
            repo_url, ref, "Quozul",
            "cccccccccccccccccccccccccccccccccccccccc", versions,
            "none", "modern", None, None, 30,
        )
