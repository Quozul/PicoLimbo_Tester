"""Tests for ``src.domain.job.Job`` aggregate root."""

import pytest
from datetime import datetime, timezone
from pathlib import Path

from src.domain.job import Job
from src.domain.value_objects import (
    ArtifactPath,
    CommitHash,
    ForwardingMethod,
    JobId,
    JobStatus,
    ProxyType,
    RepoUrl,
    TestResult,
    Version,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(**overrides) -> Job:
    """Create a minimal Job with sensible defaults, then override."""
    defaults = {
        "job_id": JobId.generate(),
        "repo_url": RepoUrl("https://github.com/Quozul/PicoLimbo.git"),
        "ref": "main",
        "commit_hash": CommitHash("deadbeef" * 5),
        "status": JobStatus.QUEUED,
        "versions": [Version(1, 21, 1, 767), Version(1, 20, 4, 766)],
        "proxy_type": ProxyType.NONE,
        "forwarding_method": ForwardingMethod.MODERN,
        "plugins": ["test-plugin.jar"],
        "login_wait_timeout": 30,
    }
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestJobConstruction:
    def test_minimal_job(self):
        job = _make_job()
        assert job.status == JobStatus.QUEUED
        assert job.test_results == {}
        assert job.artifact_path is None
        assert job.plugins == ["test-plugin.jar"]
        assert job.login_wait_timeout == 30

    def test_job_with_all_fields(self):
        artifact = ArtifactPath(Path("/tmp/artifact.jar"))
        job = _make_job(
            artifact_path=artifact,
            test_results={"1.21.1": TestResult(Version(1, 21, 1, 767), True)},
        )
        assert job.artifact_path == artifact
        assert "1.21.1" in job.test_results

    def test_job_with_no_plugins(self):
        job = _make_job(plugins=None)
        assert job.plugins is None

    def test_created_at_and_updated_at_are_utc(self):
        job = _make_job()
        assert job.created_at.tzinfo is not None
        assert job.updated_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_dict_contains_expected_keys(self):
        job = _make_job()
        d = job.to_dict()
        expected_keys = {
            "job_id", "repo_url", "ref", "owner", "commit_hash",
            "status", "versions", "proxy", "forwarding_method",
            "plugins", "login_wait_timeout", "test_results",
            "artifact_path", "created_at", "updated_at",
            "current_step", "error_message", "eta_seconds",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values(self):
        job = _make_job(
            artifact_path=ArtifactPath(Path("/tmp/artifact.jar")),
            plugins=["a.jar", "b.jar"],
        )
        d = job.to_dict()
        assert d["job_id"] == job.job_id.value
        assert d["repo_url"] == "https://github.com/Quozul/PicoLimbo.git"
        assert d["owner"] == "Quozul"
        assert d["commit_hash"] == "deadbeef" * 5
        assert d["status"] == JobStatus.QUEUED
        assert d["versions"] == ["1.21.1", "1.20.4"]
        assert d["proxy"] == "none"
        assert d["forwarding_method"] == "modern"
        assert d["plugins"] == ["a.jar", "b.jar"]
        assert d["login_wait_timeout"] == 30
        assert d["artifact_path"] == "/tmp/artifact.jar"

    def test_to_dict_no_artifact(self):
        job = _make_job(artifact_path=None)
        d = job.to_dict()
        assert d["artifact_path"] is None

    def test_to_dict_no_plugins(self):
        job = _make_job(plugins=None)
        d = job.to_dict()
        assert d["plugins"] is None

    def test_round_trip(self):
        original = _make_job(
            artifact_path=ArtifactPath(Path("/tmp/artifact.jar")),
            test_results={
                "1.21.1": TestResult(
                    Version(1, 21, 1, 767),
                    passed=True,
                    screenshot_path=Path("/tmp/ss.png"),
                    duration_seconds=5.0,
                ),
            },
        )
        d = original.to_dict()
        restored = Job.from_dict(d)

        assert restored.job_id.value == original.job_id.value
        assert restored.repo_url.value == original.repo_url.value
        assert restored.ref == original.ref
        assert restored.commit_hash.value == original.commit_hash.value
        assert restored.status == original.status
        assert restored.versions == original.versions
        assert restored.proxy_type == original.proxy_type
        assert restored.forwarding_method == original.forwarding_method
        assert restored.plugins == original.plugins
        assert restored.login_wait_timeout == original.login_wait_timeout
        assert restored.artifact_path == original.artifact_path
        assert list(restored.test_results.keys()) == list(original.test_results.keys())
        for v_str, r in restored.test_results.items():
            assert r.passed == original.test_results[v_str].passed
            assert r.screenshot_path == original.test_results[v_str].screenshot_path
            assert r.duration_seconds == original.test_results[v_str].duration_seconds

    def test_round_trip_empty_test_results(self):
        job = _make_job()
        d = job.to_dict()
        restored = Job.from_dict(d)
        assert restored.test_results == {}


# ---------------------------------------------------------------------------
# State machine transitions
# ---------------------------------------------------------------------------

class TestStateTransitions:
    def test_queued_to_building(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        assert job.status == JobStatus.BUILDING

    def test_building_to_testing(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        job.artifact_path = ArtifactPath(Path("/tmp/artifact.jar"))
        job.transition_to(JobStatus.TESTING)
        assert job.status == JobStatus.TESTING

    def test_building_to_failed(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        job.transition_to(JobStatus.FAILED)
        assert job.status == JobStatus.FAILED

    def test_testing_to_finished(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        job.artifact_path = ArtifactPath(Path("/tmp/artifact.jar"))
        job.transition_to(JobStatus.TESTING)
        job.transition_to(JobStatus.FINISHED)
        assert job.status == JobStatus.FINISHED

    def test_testing_to_failed(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        job.artifact_path = ArtifactPath(Path("/tmp/artifact.jar"))
        job.transition_to(JobStatus.TESTING)
        job.transition_to(JobStatus.FAILED)
        assert job.status == JobStatus.FAILED

    def test_invalid_queued_to_testing(self):
        job = _make_job()
        with pytest.raises(ValueError, match="Invalid transition"):
            job.transition_to(JobStatus.TESTING)

    def test_invalid_queued_to_finished(self):
        job = _make_job()
        with pytest.raises(ValueError, match="Invalid transition"):
            job.transition_to(JobStatus.FINISHED)

    def test_invalid_building_to_queued(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        with pytest.raises(ValueError, match="Invalid transition"):
            job.transition_to(JobStatus.QUEUED)

    def test_invalid_testing_to_building(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        job.artifact_path = ArtifactPath(Path("/tmp/artifact.jar"))
        job.transition_to(JobStatus.TESTING)
        with pytest.raises(ValueError, match="Invalid transition"):
            job.transition_to(JobStatus.BUILDING)

    def test_updated_at_changes_on_transition(self):
        job = _make_job()
        old_updated = job.updated_at
        import time
        time.sleep(0.01)
        job.transition_to(JobStatus.BUILDING)
        assert job.updated_at > old_updated


# ---------------------------------------------------------------------------
# Invariant enforcement
# ---------------------------------------------------------------------------

class TestInvariants:
    def test_testing_without_artifact_fails(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        with pytest.raises(ValueError, match="artifact_path"):
            job.transition_to(JobStatus.TESTING)

    def test_building_with_test_results_fails(self):
        job = _make_job(
            test_results={"1.21.1": TestResult(Version(1, 21, 1, 767), True)}
        )
        with pytest.raises(ValueError, match="test_results"):
            job.transition_to(JobStatus.BUILDING)

    def test_terminal_state_cannot_transition(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        job.artifact_path = ArtifactPath(Path("/tmp/artifact.jar"))
        job.transition_to(JobStatus.TESTING)
        job.transition_to(JobStatus.FINISHED)
        with pytest.raises(ValueError, match="terminal state"):
            job.transition_to(JobStatus.QUEUED)

    def test_failed_is_terminal(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        job.transition_to(JobStatus.FAILED)
        with pytest.raises(ValueError, match="terminal state"):
            job.transition_to(JobStatus.TESTING)


# ---------------------------------------------------------------------------
# add_test_result
# ---------------------------------------------------------------------------

class TestAddTestResult:
    def test_add_during_testing(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        job.artifact_path = ArtifactPath(Path("/tmp/artifact.jar"))
        job.transition_to(JobStatus.TESTING)
        r = TestResult(Version(1, 21, 1, 767), True, duration_seconds=5.0)
        job.add_test_result(r)
        assert "1.21.1" in job.test_results
        assert job.test_results["1.21.1"].passed is True

    def test_add_during_finished(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        job.artifact_path = ArtifactPath(Path("/tmp/artifact.jar"))
        job.transition_to(JobStatus.TESTING)
        job.transition_to(JobStatus.FINISHED)
        r = TestResult(Version(1, 20, 4, 766), False, error="Crash")
        job.add_test_result(r)
        assert "1.20.4" in job.test_results

    def test_add_during_queued_fails(self):
        job = _make_job()
        r = TestResult(Version(1, 21, 1, 767), True)
        with pytest.raises(ValueError, match="Cannot add test results"):
            job.add_test_result(r)

    def test_add_during_building_fails(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        r = TestResult(Version(1, 21, 1, 767), True)
        with pytest.raises(ValueError, match="Cannot add test results"):
            job.add_test_result(r)

    def test_add_during_failed_fails(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        job.transition_to(JobStatus.FAILED)
        r = TestResult(Version(1, 21, 1, 767), True)
        with pytest.raises(ValueError, match="Cannot add test results"):
            job.add_test_result(r)

    def test_add_replaces_existing_version(self):
        job = _make_job()
        job.transition_to(JobStatus.BUILDING)
        job.artifact_path = ArtifactPath(Path("/tmp/artifact.jar"))
        job.transition_to(JobStatus.TESTING)
        r1 = TestResult(Version(1, 21, 1, 767), True)
        r2 = TestResult(Version(1, 21, 1, 767), False, error="New error")
        job.add_test_result(r1)
        job.add_test_result(r2)
        assert len(job.test_results) == 1
        assert job.test_results["1.21.1"].passed is False
        assert job.test_results["1.21.1"].error == "New error"


# ---------------------------------------------------------------------------
# Owner extraction
# ---------------------------------------------------------------------------

class TestOwnerExtraction:
    def test_to_dict_includes_owner(self):
        job = _make_job()
        d = job.to_dict()
        assert d["owner"] == "Quozul"

    def test_to_dict_owner_from_url(self):
        job = _make_job(
            repo_url=RepoUrl("https://github.com/someorg/somerepo.git")
        )
        d = job.to_dict()
        assert d["owner"] == "someorg"
