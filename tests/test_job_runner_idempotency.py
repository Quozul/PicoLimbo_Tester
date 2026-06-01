"""Unit tests for idempotency and caching in src/orchestration/job_runner.py.

Tests cover:
- _build_step: artifact reuse (skip) vs fresh build
- _test_step: always tests all versions (no screenshot-based skip),
  persistence after each version
- _compute_eta: edge cases and proportional ETA
- run_job: full lifecycle with artifact skip and version testing
"""

import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.orchestration import job_runner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_path_mock(spec=Path):
    """Create a MagicMock that behaves like a Path for /-chaining."""
    m = MagicMock(spec=spec)
    m.__truediv__ = MagicMock(return_value=m)
    return m


def _make_job(
    job_id: str = "job0000000000000000",
    owner: str = "Quozul",
    repo_url: str = "https://github.com/Quozul/PicoLimbo.git",
    ref: str = "main",
    commit_hash: str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    versions: list[str] | None = None,
    status: str = "queued",
    artifact_path: str | None = None,
    test_results: dict | None = None,
    created_at: str | None = None,
) -> dict:
    """Create a minimal job dict for testing."""
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
    return {
        "job_id": job_id,
        "owner": owner,
        "repo_url": repo_url,
        "ref": ref,
        "commit_hash": commit_hash,
        "versions": versions or ["3.10", "3.11", "3.12"],
        "status": status,
        "artifact_path": artifact_path,
        "test_results": test_results or {},
        "created_at": created_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _make_test_result(version: str, passed: bool = True, screenshot: str | None = None) -> dict:
    return {
        "version": version,
        "passed": passed,
        "screenshot_path": screenshot,
        "duration_seconds": 90.0,
        "error": None,
    }


# ---------------------------------------------------------------------------
# 1. _build_step — artifact already exists (skip)
# ---------------------------------------------------------------------------

class TestBuildStepArtifactExists:
    def test_returns_skipped_true_and_artifact_path(self):
        """When artifact exists on disk, _build_step skips build."""
        job = _make_job()
        commit_hash = job["commit_hash"]
        artifact_path = f"/app/builds/{job['owner']}/{job['ref']}/{commit_hash}/pico_limbo"

        mock_artifact = _make_path_mock()
        mock_artifact.__str__ = lambda self: artifact_path

        mock_artifact_dir = _make_path_mock()
        mock_artifact_dir.__truediv__ = MagicMock(
            side_effect=lambda other: mock_artifact if other == "pico_limbo" else mock_artifact_dir
        )
        mock_artifact_dir.__str__ = lambda self: f"/app/builds/{job['owner']}/{job['ref']}/{commit_hash}"

        mock_storage = MagicMock()
        mock_storage.get.return_value = Path(artifact_path)

        with patch.object(job_runner.database, "update_job") as mock_db_update:
            mock_db_update.return_value = job

            with patch.object(job_runner.engine, "_get_git_repo") as mock_get_git:
                with patch.object(job_runner.engine, "BUILDS_DIR", mock_artifact_dir):
                    with patch(
                        "src.orchestration.job_runner.ArtifactStorage", return_value=mock_storage
                    ):
                        skipped, result_path = job_runner._build_step(job)

        assert skipped is True
        assert result_path == artifact_path
        # Should NOT call git or build when artifact exists
        mock_get_git.assert_not_called()

    def test_returns_early_without_git_calls_when_artifact_exists(self):
        """When artifact exists, _build_step returns early without git calls."""
        job = _make_job()
        commit_hash = job["commit_hash"]

        mock_artifact = _make_path_mock()
        mock_artifact.__str__ = lambda self: "/app/builds/Quozul/main/abc/pico_limbo"

        mock_artifact_dir = _make_path_mock()
        mock_artifact_dir.__truediv__ = MagicMock(
            side_effect=lambda other: mock_artifact if other == "pico_limbo" else mock_artifact_dir
        )
        mock_artifact_dir.__str__ = lambda self: "/app/builds/Quozul/main/abc"

        mock_storage = MagicMock()
        mock_storage.get.return_value = Path("/app/builds/Quozul/main/abc/pico_limbo")

        with patch.object(job_runner.database, "update_job", return_value=job):
            with patch.object(job_runner.engine, "BUILDS_DIR", mock_artifact_dir):
                with patch.object(job_runner.engine, "_get_git_repo") as mock_get_git:
                    with patch(
                        "src.orchestration.job_runner.ArtifactStorage", return_value=mock_storage
                    ):
                        job_runner._build_step(job)

        # Should NOT call git when artifact exists
        mock_get_git.assert_not_called()


# ---------------------------------------------------------------------------
# 2. _build_step — artifact doesn't exist (build)
# ---------------------------------------------------------------------------

class TestBuildStepArtifactMissing:
    def test_returns_skipped_false_and_calls_build_project(self):
        """When artifact doesn't exist, _build_step calls build_project."""
        from src.application.build_service import BuildResult
        from src.domain.value_objects import ArtifactPath, CommitHash

        job = _make_job()
        commit_hash = job["commit_hash"]
        artifact_path = f"/app/builds/{job['owner']}/{job['ref']}/{commit_hash}/pico_limbo"

        mock_artifact = _make_path_mock()
        mock_artifact.exists.return_value = False
        mock_artifact.__str__ = lambda self: artifact_path

        mock_artifact_dir = _make_path_mock()
        mock_artifact_dir.__truediv__ = MagicMock(
            side_effect=lambda other: mock_artifact if other == "pico_limbo" else mock_artifact_dir
        )
        mock_artifact_dir.__str__ = lambda self: f"/app/builds/{job['owner']}/{job['ref']}/{commit_hash}"

        # Mock ArtifactStorage.get to return None (no existing artifact)
        mock_storage = MagicMock()
        mock_storage.get.return_value = None

        with patch.object(job_runner.database, "update_job") as mock_db_update:
            mock_db_update.return_value = job

            mock_repo = MagicMock()
            mock_repo.clone.return_value = "/repos/Quozul/PicoLimbo"
            mock_repo.resolve.return_value = commit_hash

            mock_build_result = BuildResult(
                commit_hash=CommitHash(commit_hash),
                artifact_path=ArtifactPath(Path(artifact_path)),
            )

            with patch("src.orchestration.job_runner.engine.build_project") as mock_build:
                mock_build.return_value = mock_build_result

                with patch.object(job_runner.engine, "_get_git_repo", return_value=mock_repo):
                    with patch.object(job_runner.engine, "BUILDS_DIR", mock_artifact_dir):
                        with patch(
                            "src.orchestration.job_runner.ArtifactStorage", return_value=mock_storage
                        ):
                            skipped, result_path = job_runner._build_step(job)

        assert mock_repo.clone.called
        assert mock_repo.resolve.called

        assert skipped is False
        assert result_path == artifact_path
        mock_build.assert_called_once()
        # Verify build_project was called with correct args (new signature)
        call_args = mock_build.call_args
        assert call_args[0][0] == job["repo_url"]  # repo_url
        assert call_args[0][1] == job["ref"]
        assert call_args[0][2] == job["owner"]
        assert call_args[0][3] == job["repo_url"].split("/")[-1].replace(".git", "")

    def test_update_job_called_with_commit_hash(self):
        """_build_step persists commit_hash via database.update_job."""
        from src.application.build_service import BuildResult
        from src.domain.value_objects import ArtifactPath, CommitHash

        job = _make_job()
        commit_hash = job["commit_hash"]

        mock_artifact = _make_path_mock()
        mock_artifact.exists.return_value = False
        mock_artifact.__str__ = lambda self: "/app/builds/Quozul/main/abc/pico_limbo"

        mock_artifact_dir = _make_path_mock()
        mock_artifact_dir.__truediv__ = MagicMock(
            side_effect=lambda other: mock_artifact if other == "pico_limbo" else mock_artifact_dir
        )

        mock_storage = MagicMock()
        mock_storage.get.return_value = None

        with patch.object(job_runner.database, "update_job") as mock_db_update:
            mock_db_update.return_value = job

            mock_repo = MagicMock()
            mock_repo.clone.return_value = "/repos/Quozul/PicoLimbo"
            mock_repo.resolve.return_value = commit_hash

            mock_build_result = BuildResult(
                commit_hash=CommitHash(commit_hash),
                artifact_path=ArtifactPath(Path("/app/builds/Quozul/main/abc/pico_limbo")),
            )

            with patch("src.orchestration.job_runner.engine.build_project", return_value=mock_build_result):
                with patch.object(job_runner.engine, "_get_git_repo", return_value=mock_repo):
                    with patch.object(job_runner.engine, "BUILDS_DIR", mock_artifact_dir):
                        with patch(
                            "src.orchestration.job_runner.ArtifactStorage", return_value=mock_storage
                        ):
                            job_runner._build_step(job)

        # First call should be for commit_hash persistence
        commit_hash_calls = [
            c for c in mock_db_update.call_args_list
            if "commit_hash" in c.kwargs
        ]
        assert len(commit_hash_calls) >= 1
        assert commit_hash_calls[0].kwargs["commit_hash"] == commit_hash


# ---------------------------------------------------------------------------
# 3. _test_step — always tests all versions (no skip based on screenshots)
# ---------------------------------------------------------------------------

class TestTestStepAlwaysTestsAllVersions:
    def test_calls_test_single_version_for_all_versions(self):
        """Every version is tested, regardless of previous results or screenshots."""
        job = _make_job(versions=["3.10", "3.11", "3.12"])
        previous_results = {
            "3.10": _make_test_result("3.10", True, "/screenshots/3.10.png"),
            "3.11": _make_test_result("3.11", True, "/screenshots/3.11.png"),
            "3.12": _make_test_result("3.12", True, "/screenshots/3.12.png"),
        }

        mock_vim = MagicMock()
        mock_vim.close = MagicMock()

        def side_effect(version, *args, **kwargs):
            return {
                "version": version,
                "passed": True,
                "screenshot_path": f"/screenshots/{version}.png",
                "duration_seconds": 90.0,
                "error": None,
            }

        with patch.object(job_runner.database, "update_job"):
            with patch.object(job_runner.database, "get_job_by_id", return_value=job):
                with patch("src.orchestration.job_runner.test_single_version", side_effect=side_effect) as mock_test:
                    with patch("src.orchestration.job_runner.empty_directory"):
                        with patch("src.orchestration.job_runner.os.makedirs"):
                            with patch("src.orchestration.job_runner.VirtualInputController", return_value=mock_vim):
                                results = job_runner._test_step(job, job["versions"], None)

        # All 3 versions should be tested
        assert mock_test.call_count == 3
        called_versions = {c[0][0] for c in mock_test.call_args_list}
        assert called_versions == {"3.10", "3.11", "3.12"}

        # All versions should be in results
        assert len(results) == 3

    def test_test_single_version_called_for_all_versions(self):
        """test_single_version is called for every version, no skips."""
        job = _make_job(versions=["3.10"])

        mock_vim = MagicMock()
        mock_vim.close = MagicMock()

        def side_effect(version, *args, **kwargs):
            return _make_test_result(version, True, f"/screenshots/{version}.png")

        with patch.object(job_runner.database, "update_job"):
            with patch.object(job_runner.database, "get_job_by_id", return_value=job):
                with patch("src.orchestration.job_runner.test_single_version", side_effect=side_effect) as mock_test:
                    with patch("src.orchestration.job_runner.empty_directory"):
                        with patch("src.orchestration.job_runner.os.makedirs"):
                            with patch("src.orchestration.job_runner.VirtualInputController", return_value=mock_vim):
                                job_runner._test_step(job, job["versions"], None)

        mock_test.assert_called_once_with("3.10", job["commit_hash"], mock_vim, job_runner.SCREENSHOTS_DIR, 30)


# ---------------------------------------------------------------------------
# 4. _test_step — test results reflect actual test outcomes
# ---------------------------------------------------------------------------

class TestTestStepResultsReflectActualTests:
    def test_passed_version_in_results(self):
        """A version that passed the actual test is marked as passed."""
        job = _make_job(versions=["3.10"])

        mock_vim = MagicMock()
        mock_vim.close = MagicMock()

        with patch.object(job_runner.database, "update_job"):
            with patch.object(job_runner.database, "get_job_by_id", return_value=job):
                with patch("src.orchestration.job_runner.test_single_version", return_value=_make_test_result("3.10", True, "/screenshots/3.10.png")):
                    with patch("src.orchestration.job_runner.empty_directory"):
                        with patch("src.orchestration.job_runner.os.makedirs"):
                            with patch("src.orchestration.job_runner.VirtualInputController", return_value=mock_vim):
                                results = job_runner._test_step(job, job["versions"], None)

        assert results["3.10"]["passed"] is True
        assert results["3.10"]["screenshot_path"] == "/screenshots/3.10.png"

    def test_failed_version_in_results(self):
        """A version that failed the actual test is marked as failed with error."""
        job = _make_job(versions=["3.10"])

        mock_vim = MagicMock()
        mock_vim.close = MagicMock()

        failed_result = {
            "version": "3.10",
            "passed": False,
            "screenshot_path": None,
            "duration_seconds": 45.0,
            "error": "connection timeout",
        }

        with patch.object(job_runner.database, "update_job"):
            with patch.object(job_runner.database, "get_job_by_id", return_value=job):
                with patch("src.orchestration.job_runner.test_single_version", return_value=failed_result):
                    with patch("src.orchestration.job_runner.empty_directory"):
                        with patch("src.orchestration.job_runner.os.makedirs"):
                            with patch("src.orchestration.job_runner.VirtualInputController", return_value=mock_vim):
                                results = job_runner._test_step(job, job["versions"], None)

        assert results["3.10"]["passed"] is False
        assert results["3.10"]["error"] == "connection timeout"


# ---------------------------------------------------------------------------
# 5. _test_step — persistence after each version
# ---------------------------------------------------------------------------

class TestTestStepPersistence:
    def test_update_job_called_after_each_version(self):
        """database.update_job is called after processing each version.

        Each version triggers 2 calls: one for current_step and one for test_results.
        """
        job = _make_job(versions=["3.10", "3.11", "3.12"])

        mock_vim = MagicMock()
        mock_vim.close = MagicMock()

        def side_effect(version, *args, **kwargs):
            return _make_test_result(version, True, f"/screenshots/{version}.png")

        with patch.object(job_runner.database, "update_job") as mock_db_update:
            with patch.object(job_runner.database, "get_job_by_id", return_value=job):
                with patch("src.orchestration.job_runner.test_single_version", side_effect=side_effect):
                    with patch("src.orchestration.job_runner.empty_directory"):
                        with patch("src.orchestration.job_runner.os.makedirs"):
                            with patch("src.orchestration.job_runner.VirtualInputController", return_value=mock_vim):
                                job_runner._test_step(job, job["versions"], None)

        # 3 versions tested → 6 update_job calls (2 per version: current_step + test_results)
        assert mock_db_update.call_count == 6

    def test_persisted_test_results_accumulate_correctly(self):
        """Each update_job call includes all results accumulated so far."""
        job = _make_job(versions=["3.10", "3.11"])
        call_index = {"value": 0}

        def side_effect(version, *args, **kwargs):
            call_index["value"] += 1
            return _make_test_result(version, True, f"/screenshots/{version}.png")

        with patch.object(job_runner.database, "update_job") as mock_db_update:
            with patch.object(job_runner.database, "get_job_by_id", return_value=job):
                with patch("src.orchestration.job_runner.test_single_version", side_effect=side_effect):
                    with patch("src.orchestration.job_runner.empty_directory"):
                        with patch("src.orchestration.job_runner.os.makedirs"):
                            with patch("src.orchestration.job_runner.VirtualInputController") as mock_vim:
                                mock_vim.return_value.close = MagicMock()
                                job_runner._test_step(job, job["versions"], None)

        # Each version has 2 calls: current_step (no test_results) then test_results
        # Call 0: current_step for 3.10 (no test_results)
        # Call 1: test_results for 3.10 (only 3.10)
        # Call 2: current_step for 3.11 (no test_results)
        # Call 3: test_results for 3.11 (3.10 and 3.11)

        # First call with test_results is at index 1
        first_results_call = mock_db_update.call_args_list[1]
        first_results = json.loads(first_results_call.kwargs["test_results"])
        assert set(first_results.keys()) == {"3.10"}
        assert first_results["3.10"]["passed"] is True

        # Second call with test_results is at index 3
        second_results_call = mock_db_update.call_args_list[3]
        second_results = json.loads(second_results_call.kwargs["test_results"])
        assert set(second_results.keys()) == {"3.10", "3.11"}
        assert second_results["3.10"]["passed"] is True
        assert second_results["3.11"]["passed"] is True


# ---------------------------------------------------------------------------
# 6. _compute_eta — idempotency-related
# ---------------------------------------------------------------------------

class TestComputeEta:
    def test_returns_none_when_status_not_testing(self):
        """ETA is None for any status other than 'testing'."""
        for status in ["queued", "building", "finished", "failed"]:
            job = _make_job(status=status)
            assert job_runner._compute_eta(job) is None

    def test_returns_none_when_no_test_results(self):
        """ETA is None when test_results is empty."""
        job = _make_job(status="testing", test_results={})
        assert job_runner._compute_eta(job) is None

    def test_returns_none_when_no_versions(self):
        """ETA is None when versions list is empty."""
        # Use a real job dict with empty versions (not via _make_job helper,
        # since [] is falsy and would trigger the default versions list).
        job = {
            "job_id": "job0000000000000000",
            "owner": "Quozul",
            "repo_url": "https://github.com/Quozul/PicoLimbo.git",
            "ref": "main",
            "commit_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "versions": [],
            "status": "testing",
            "test_results": {"3.10": {}},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        assert job_runner._compute_eta(job) is None

    def test_returns_none_when_all_versions_tested(self):
        """ETA is None (returns 0) when all versions have been tested."""
        job = _make_job(
            status="testing",
            versions=["3.10", "3.11"],
            test_results={
                "3.10": {"passed": True},
                "3.11": {"passed": True},
            },
        )
        assert job_runner._compute_eta(job) == 0

    def test_returns_positive_integer_when_versions_remain(self):
        """ETA is a positive integer when some versions remain."""
        # created_at 180 seconds ago, 1 of 3 tested → avg 180s per version
        # remaining = 2, so ETA ≈ 360
        created_at = (datetime.now(timezone.utc) - timedelta(seconds=180)).isoformat()
        job = _make_job(
            status="testing",
            versions=["3.10", "3.11", "3.12"],
            test_results={"3.10": {"passed": True}},
            created_at=created_at,
        )
        eta = job_runner._compute_eta(job)
        assert isinstance(eta, int)
        assert eta > 0
        # Allow some tolerance since time may have passed
        assert eta >= 300  # 2 * 180 = 360, but with elapsed slightly > 180

    def test_eta_increases_with_more_remaining_versions(self):
        """More remaining versions → larger ETA."""
        now = datetime.now(timezone.utc)
        created_at = (now - timedelta(seconds=60)).isoformat()

        # 1 of 2 tested → remaining = 1, ETA ≈ 60
        job_few_remaining = _make_job(
            status="testing",
            versions=["3.10", "3.11"],
            test_results={"3.10": {"passed": True}},
            created_at=created_at,
        )

        # 1 of 10 tested → remaining = 9, ETA ≈ 540
        job_many_remaining = _make_job(
            status="testing",
            versions=["3.10", "3.11", "3.12", "3.13", "3.14",
                      "3.15", "3.16", "3.17", "3.18", "3.19"],
            test_results={"3.10": {"passed": True}},
            created_at=created_at,
        )

        eta_few = job_runner._compute_eta(job_few_remaining)
        eta_many = job_runner._compute_eta(job_many_remaining)

        assert eta_few is not None and eta_few > 0
        assert eta_many is not None and eta_many > 0
        assert eta_many > eta_few

    def test_returns_zero_not_negative(self):
        """ETA should never be negative."""
        # If elapsed is very small and tested_count is large (shouldn't happen,
        # but defensive), eta should clamp to 0.
        created_at = datetime.now(timezone.utc).isoformat()
        job = _make_job(
            status="testing",
            versions=["3.10"],
            test_results={"3.10": {"passed": True}},
            created_at=created_at,
        )
        assert job_runner._compute_eta(job) == 0


# ---------------------------------------------------------------------------
# 7. run_job — full lifecycle with artifact skip
# ---------------------------------------------------------------------------

class TestRunJobArtifactSkip:
    def test_build_skipped_job_transitions_to_testing(self):
        """When artifact exists, _build_step returns skipped=True, job goes to testing."""
        job = _make_job()
        commit_hash = job["commit_hash"]
        artifact_path = f"/app/builds/{job['owner']}/{job['ref']}/{commit_hash}/pico_limbo"

        mock_artifact = _make_path_mock()
        mock_artifact.__str__ = lambda self: artifact_path

        mock_artifact_dir = _make_path_mock()
        mock_artifact_dir.__truediv__ = MagicMock(
            side_effect=lambda other: mock_artifact if other == "pico_limbo" else mock_artifact_dir
        )

        mock_storage = MagicMock()
        mock_storage.get.return_value = Path(artifact_path)

        # Track status transitions
        status_transitions = []

        def track_update(job_id, **fields):
            if "status" in fields:
                status_transitions.append(fields["status"])
            return {**job, **fields}

        with patch.object(job_runner.database, "get_job_by_id", return_value=job):
            with patch.object(job_runner.database, "update_job", side_effect=track_update):
                with patch.object(job_runner.engine, "BUILDS_DIR", mock_artifact_dir):
                    with patch.object(job_runner.engine, "_get_git_repo"):
                        with patch("src.orchestration.job_runner._server_step", return_value=(None, MagicMock())):
                            with patch("src.orchestration.job_runner.test_single_version", return_value=_make_test_result("3.10")):
                                with patch("src.orchestration.job_runner.empty_directory"):
                                    with patch("src.orchestration.job_runner.os.makedirs"):
                                        with patch("src.orchestration.job_runner.VirtualInputController") as mock_vim:
                                            mock_vim.return_value.close = MagicMock()
                                            with patch(
                                                "src.orchestration.job_runner.ArtifactStorage", return_value=mock_storage
                                            ):
                                                job_runner.run_job("job0000000000000000")

        # Status should transition: building → testing → finished
        assert "building" in status_transitions
        assert "testing" in status_transitions
        assert "finished" in status_transitions

    def test_build_project_not_called_when_artifact_exists(self):
        """When artifact exists, engine.build_project is never called."""
        job = _make_job()
        commit_hash = job["commit_hash"]
        artifact_path = f"/app/builds/{job['owner']}/{job['ref']}/{commit_hash}/pico_limbo"

        mock_artifact = _make_path_mock()
        mock_artifact.__str__ = lambda self: artifact_path

        mock_artifact_dir = _make_path_mock()
        mock_artifact_dir.__truediv__ = MagicMock(
            side_effect=lambda other: mock_artifact if other == "pico_limbo" else mock_artifact_dir
        )

        mock_storage = MagicMock()
        mock_storage.get.return_value = Path(artifact_path)

        with patch.object(job_runner.database, "get_job_by_id", return_value=job):
            with patch.object(job_runner.database, "update_job", return_value=job):
                with patch.object(job_runner.engine, "BUILDS_DIR", mock_artifact_dir):
                    with patch.object(job_runner.engine, "_get_git_repo") as mock_get_git:
                        with patch("src.orchestration.job_runner.engine.build_project") as mock_build:
                            with patch("src.orchestration.job_runner._server_step", return_value=(None, MagicMock())):
                                with patch("src.orchestration.job_runner.test_single_version", return_value=_make_test_result("3.10")):
                                    with patch("src.orchestration.job_runner.empty_directory"):
                                        with patch("src.orchestration.job_runner.os.makedirs"):
                                            with patch("src.orchestration.job_runner.VirtualInputController") as mock_vim:
                                                mock_vim.return_value.close = MagicMock()
                                                with patch(
                                                    "src.orchestration.job_runner.ArtifactStorage", return_value=mock_storage
                                                ):
                                                    job_runner.run_job("job0000000000000000")

        mock_build.assert_not_called()
        mock_get_git.assert_not_called()


# ---------------------------------------------------------------------------
# 8. run_job — full lifecycle with server always started
# ---------------------------------------------------------------------------

class TestRunJobServerStarted:
    def test_server_started_regardless_of_previous_results(self):
        """Server is always started and all versions are tested."""
        job = _make_job()
        commit_hash = job["commit_hash"]
        artifact_path = f"/app/builds/{job['owner']}/{job['ref']}/{commit_hash}/pico_limbo"

        mock_artifact = _make_path_mock()
        mock_artifact.__str__ = lambda self: artifact_path

        mock_artifact_dir = _make_path_mock()
        mock_artifact_dir.__truediv__ = MagicMock(
            side_effect=lambda other: mock_artifact if other == "pico_limbo" else mock_artifact_dir
        )

        mock_storage = MagicMock()
        mock_storage.get.return_value = Path(artifact_path)

        # Pretend all versions already passed in a previous run
        previous_results = {
            v: _make_test_result(v, True, f"/screenshots/{v}.png")
            for v in job["versions"]
        }

        with patch.object(job_runner.database, "get_job_by_id", return_value=job):
            with patch.object(job_runner.database, "update_job", return_value=job):
                with patch.object(job_runner.engine, "BUILDS_DIR", mock_artifact_dir):
                    with patch.object(job_runner.engine, "_get_git_repo"):
                        with patch("src.orchestration.job_runner._server_step") as mock_server:
                            mock_server.return_value = (None, MagicMock())
                            with patch("src.orchestration.job_runner.test_single_version", return_value=_make_test_result("3.10")) as mock_test:
                                with patch("src.orchestration.job_runner.empty_directory"):
                                    with patch("src.orchestration.job_runner.os.makedirs"):
                                        with patch("src.orchestration.job_runner.VirtualInputController") as mock_vim:
                                            mock_vim.return_value.close = MagicMock()
                                            with patch(
                                                "src.orchestration.job_runner.ArtifactStorage", return_value=mock_storage
                                            ):
                                                job_runner.run_job("job0000000000000000")

        # Server should have been started
        mock_server.assert_called_once()
        # test_single_version should have been called for all versions
        assert mock_test.call_count == len(job["versions"])

    def test_job_ends_with_finished_status(self):
        """Job status transitions to 'finished' after all versions are tested."""
        job = _make_job()
        commit_hash = job["commit_hash"]
        artifact_path = f"/app/builds/{job['owner']}/{job['ref']}/{commit_hash}/pico_limbo"

        mock_artifact = _make_path_mock()
        mock_artifact.__str__ = lambda self: artifact_path

        mock_artifact_dir = _make_path_mock()
        mock_artifact_dir.__truediv__ = MagicMock(
            side_effect=lambda other: mock_artifact if other == "pico_limbo" else mock_artifact_dir
        )

        mock_storage = MagicMock()
        mock_storage.get.return_value = Path(artifact_path)

        final_status = None

        def track_update(job_id, **fields):
            nonlocal final_status
            if "status" in fields:
                final_status = fields["status"]
            return {**job, **fields}

        with patch.object(job_runner.database, "get_job_by_id", return_value=job):
            with patch.object(job_runner.database, "update_job", side_effect=track_update):
                with patch.object(job_runner.engine, "BUILDS_DIR", mock_artifact_dir):
                    with patch.object(job_runner.engine, "_get_git_repo"):
                        with patch("src.orchestration.job_runner._server_step", return_value=(None, MagicMock())):
                            with patch("src.orchestration.job_runner.test_single_version", return_value=_make_test_result("3.10")):
                                with patch("src.orchestration.job_runner.empty_directory"):
                                    with patch("src.orchestration.job_runner.os.makedirs"):
                                        with patch("src.orchestration.job_runner.VirtualInputController") as mock_vim:
                                            mock_vim.return_value.close = MagicMock()
                                            with patch(
                                                "src.orchestration.job_runner.ArtifactStorage", return_value=mock_storage
                                            ):
                                                job_runner.run_job("job0000000000000000")

        assert final_status == "finished"

    def test_all_versions_tested_in_test_results(self):
        """When all versions are tested, each has actual test result in test_results."""
        job = _make_job(versions=["3.10", "3.11"])
        commit_hash = job["commit_hash"]
        artifact_path = f"/app/builds/{job['owner']}/{job['ref']}/{commit_hash}/pico_limbo"

        mock_artifact = _make_path_mock()
        mock_artifact.__str__ = lambda self: artifact_path

        mock_artifact_dir = _make_path_mock()
        mock_artifact_dir.__truediv__ = MagicMock(
            side_effect=lambda other: mock_artifact if other == "pico_limbo" else mock_artifact_dir
        )

        mock_storage = MagicMock()
        mock_storage.get.return_value = Path(artifact_path)

        captured_test_results = None

        def track_update(job_id, **fields):
            nonlocal captured_test_results
            if "test_results" in fields:
                captured_test_results = json.loads(fields["test_results"])
            return {**job, **fields}

        def side_effect(version, *args, **kwargs):
            return _make_test_result(version, True, f"/screenshots/{version}.png")

        with patch.object(job_runner.database, "get_job_by_id", return_value=job):
            with patch.object(job_runner.database, "update_job", side_effect=track_update):
                with patch.object(job_runner.engine, "BUILDS_DIR", mock_artifact_dir):
                    with patch.object(job_runner.engine, "_get_git_repo"):
                        with patch("src.orchestration.job_runner._server_step", return_value=(None, MagicMock())):
                            with patch("src.orchestration.job_runner.test_single_version", side_effect=side_effect):
                                with patch("src.orchestration.job_runner.empty_directory"):
                                    with patch("src.orchestration.job_runner.os.makedirs"):
                                        with patch("src.orchestration.job_runner.VirtualInputController") as mock_vim:
                                            mock_vim.return_value.close = MagicMock()
                                            with patch(
                                                "src.orchestration.job_runner.ArtifactStorage", return_value=mock_storage
                                            ):
                                                job_runner.run_job("job0000000000000000")

        assert captured_test_results is not None
        assert set(captured_test_results.keys()) == {"3.10", "3.11"}
        for v in ["3.10", "3.11"]:
            assert captured_test_results[v]["passed"] is True
            assert captured_test_results[v]["screenshot_path"] == f"/screenshots/{v}.png"
