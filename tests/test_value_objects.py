"""Tests for ``src.domain.value_objects``."""

import pytest
from pathlib import Path

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
    is_commit_hash,
)


# ---------------------------------------------------------------------------
# JobId
# ---------------------------------------------------------------------------

class TestJobId:
    def test_generate_returns_non_empty_id(self):
        job_id = JobId.generate()
        assert job_id.value is not None
        assert len(job_id.value) > 0

    def test_generate_returns_uuid_format(self):
        job_id = JobId.generate()
        # UUIDs contain hyphens
        assert "-" in job_id.value

    def test_generate_returns_unique_ids(self):
        ids = {JobId.generate().value for _ in range(10)}
        assert len(ids) == 10

    def test_equality(self):
        a = JobId("abc123")
        b = JobId("abc123")
        assert a == b

    def test_inequality(self):
        a = JobId("abc123")
        b = JobId("def456")
        assert a != b

    def test_frozen(self):
        job_id = JobId("abc")
        with pytest.raises(AttributeError):
            job_id.value = "new"


# ---------------------------------------------------------------------------
# RepoUrl
# ---------------------------------------------------------------------------

class TestRepoUrl:
    def test_parse_valid_url(self):
        owner, repo = RepoUrl.parse("https://github.com/Quozul/PicoLimbo.git")
        assert owner == "Quozul"
        assert repo == "PicoLimbo"

    def test_parse_valid_url_without_git_suffix(self):
        owner, repo = RepoUrl.parse("https://github.com/foo/bar")
        assert owner == "foo"
        assert repo == "bar"

    def test_parse_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Only GitHub repository URLs"):
            RepoUrl.parse("https://gitlab.com/foo/bar")

    def test_parse_non_github_url_raises(self):
        with pytest.raises(ValueError, match="Only GitHub repository URLs"):
            RepoUrl.parse("https://bitbucket.org/foo/bar")

    def test_value_is_stored(self):
        url = RepoUrl("https://github.com/foo/bar")
        assert url.value == "https://github.com/foo/bar"

    def test_frozen(self):
        url = RepoUrl("https://github.com/foo/bar")
        with pytest.raises(AttributeError):
            url.value = "https://github.com/baz/qux"


# ---------------------------------------------------------------------------
# CommitHash
# ---------------------------------------------------------------------------

class TestCommitHash:
    def test_valid_hash(self):
        h = CommitHash("deadbeef" * 5)
        assert h.value == "deadbeef" * 5

    def test_valid_hash_uppercase(self):
        h = CommitHash("DEADBEEF" * 5)
        assert h.value == "DEADBEEF" * 5

    def test_valid_hash_mixed_case(self):
        h = CommitHash("DeAdBeEf" * 5)
        assert h.value == "DeAdBeEf" * 5

    def test_invalid_too_short(self):
        with pytest.raises(ValueError, match="Invalid commit hash"):
            CommitHash("abc123")

    def test_invalid_too_long(self):
        with pytest.raises(ValueError, match="Invalid commit hash"):
            CommitHash("deadbeef" * 6)

    def test_invalid_non_hex(self):
        with pytest.raises(ValueError, match="Invalid commit hash"):
            CommitHash("g" * 40)

    def test_invalid_empty(self):
        with pytest.raises(ValueError, match="Invalid commit hash"):
            CommitHash("")

    def test_frozen(self):
        h = CommitHash("deadbeef" * 5)
        with pytest.raises(AttributeError):
            h.value = "beefdead" * 5


# ---------------------------------------------------------------------------
# ArtifactPath
# ---------------------------------------------------------------------------

class TestArtifactPath:
    def test_wraps_path(self):
        p = ArtifactPath(Path("/tmp/artifact.jar"))
        assert p.value == Path("/tmp/artifact.jar")

    def test_wraps_relative_path(self):
        p = ArtifactPath(Path("build/pico_limbo"))
        assert p.value == Path("build/pico_limbo")

    def test_frozen(self):
        p = ArtifactPath(Path("/tmp/x"))
        with pytest.raises(AttributeError):
            p.value = Path("/tmp/y")


# ---------------------------------------------------------------------------
# TestResult
# ---------------------------------------------------------------------------

class TestTestResult:
    def test_creation_defaults(self):
        v = Version(1, 21, 1, 767)
        r = TestResult(version=v, passed=True)
        assert r.version == v
        assert r.passed is True
        assert r.screenshot_path is None
        assert r.duration_seconds == 0.0
        assert r.error is None

    def test_creation_with_all_fields(self):
        v = Version(1, 16, 5, 754)
        r = TestResult(
            version=v,
            passed=False,
            screenshot_path=Path("/tmp/screenshot.png"),
            duration_seconds=12.5,
            error="Connection refused",
        )
        assert r.version == v
        assert r.passed is False
        assert r.screenshot_path == Path("/tmp/screenshot.png")
        assert r.duration_seconds == 12.5
        assert r.error == "Connection refused"

    def test_to_dict(self):
        v = Version(1, 21, 1, 767)
        r = TestResult(
            version=v,
            passed=True,
            screenshot_path=Path("/tmp/ss.png"),
            duration_seconds=5.0,
            error=None,
        )
        d = r.to_dict()
        assert d["version"] == "1.21.1"
        assert d["passed"] is True
        assert d["screenshot_path"] == "/tmp/ss.png"
        assert d["duration_seconds"] == 5.0
        assert d["error"] is None

    def test_to_dict_no_screenshot(self):
        v = Version(1, 21, 1, 767)
        r = TestResult(version=v, passed=True)
        d = r.to_dict()
        assert d["screenshot_path"] is None

    def test_from_dict(self):
        data = {
            "version": "1.21.1",
            "passed": True,
            "screenshot_path": "/tmp/ss.png",
            "duration_seconds": 5.0,
            "error": None,
        }
        r = TestResult.from_dict(data, "1.21.1")
        assert r.version == Version(1, 21, 1, 767)
        assert r.passed is True
        assert r.screenshot_path == Path("/tmp/ss.png")
        assert r.duration_seconds == 5.0

    def test_from_dict_missing_screenshot(self):
        data = {
            "version": "1.21",
            "passed": False,
            "screenshot_path": None,
            "duration_seconds": 0.0,
            "error": "Timeout",
        }
        r = TestResult.from_dict(data, "1.21")
        assert r.screenshot_path is None
        assert r.error == "Timeout"


# ---------------------------------------------------------------------------
# JobStatus
# ---------------------------------------------------------------------------

class TestJobStatus:
    def test_queued(self):
        assert JobStatus.QUEUED == "queued"

    def test_building(self):
        assert JobStatus.BUILDING == "building"

    def test_testing(self):
        assert JobStatus.TESTING == "testing"

    def test_finished(self):
        assert JobStatus.FINISHED == "finished"

    def test_failed(self):
        assert JobStatus.FAILED == "failed"


# ---------------------------------------------------------------------------
# ProxyType
# ---------------------------------------------------------------------------

class TestProxyType:
    def test_none(self):
        assert ProxyType.NONE == "none"

    def test_velocity(self):
        assert ProxyType.VELOCITY == "velocity"

    def test_bungeecord(self):
        assert ProxyType.BUNGEECORD == "bungeecord"


# ---------------------------------------------------------------------------
# ForwardingMethod
# ---------------------------------------------------------------------------

class TestForwardingMethod:
    def test_none(self):
        assert ForwardingMethod.NONE == "none"

    def test_legacy(self):
        assert ForwardingMethod.LEGACY == "legacy"

    def test_bungeeguard(self):
        assert ForwardingMethod.BUNGEEGUARD == "bungeeguard"

    def test_modern(self):
        assert ForwardingMethod.MODERN == "modern"


# ---------------------------------------------------------------------------
# is_commit_hash
# ---------------------------------------------------------------------------

class TestIsCommitHash:
    def test_valid_lowercase(self):
        assert is_commit_hash("deadbeef" * 5) is True

    def test_valid_uppercase(self):
        assert is_commit_hash("DEADBEEF" * 5) is True

    def test_invalid_too_short(self):
        assert is_commit_hash("abc123") is False

    def test_invalid_too_long(self):
        assert is_commit_hash("deadbeef" * 6) is False

    def test_invalid_non_hex(self):
        assert is_commit_hash("g" * 40) is False

    def test_invalid_empty(self):
        assert is_commit_hash("") is False

    def test_invalid_with_spaces(self):
        assert is_commit_hash("dead beef" * 5) is False
