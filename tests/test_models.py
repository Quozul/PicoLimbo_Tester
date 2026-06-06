"""Unit tests for Pydantic models in src/models.py."""

import pytest
from pydantic import ValidationError

from src.models import JobCreate, JobInfo, TestResult


class TestJobCreate:
    """Tests for the JobCreate request model."""

    def test_defaults_repo_url(self):
        job = JobCreate()
        assert job.repo_url == "https://github.com/Quozul/PicoLimbo.git"

    def test_defaults_ref(self):
        job = JobCreate()
        assert job.ref == "master"

    def test_defaults_plugins_to_none(self):
        job = JobCreate()
        assert job.plugins is None

    def test_accepts_plugins_list(self):
        job = JobCreate(plugins=["my-plugin.jar"])
        assert job.plugins == ["my-plugin.jar"]

    def test_defaults_proxy_to_none(self):
        job = JobCreate()
        assert job.proxy == "none"

    def test_defaults_forwarding_method_to_modern(self):
        job = JobCreate()
        assert job.forwarding_method == "modern"

    def test_defaults_login_wait_timeout(self):
        job = JobCreate()
        assert job.login_wait_timeout == 30

    def test_accepts_custom_values(self):
        job = JobCreate(
            repo_url="https://github.com/test/repo.git",
            ref="main",
            versions=["1.20", "1.19"],
            proxy="velocity",
            forwarding_method="bungeeguard",
            plugins=["plugin1.jar", "plugin2.jar"],
            login_wait_timeout=60,
        )
        assert job.repo_url == "https://github.com/test/repo.git"
        assert job.ref == "main"
        assert job.versions == ["1.20", "1.19"]
        assert job.proxy == "velocity"
        assert job.forwarding_method == "bungeeguard"
        assert job.plugins == ["plugin1.jar", "plugin2.jar"]
        assert job.login_wait_timeout == 60


class TestTestResultModel:
    """Tests for the TestResult response model."""

    def test_defaults_screenshot_path(self):
        result = TestResult(version="1.21.8", passed=True)
        assert result.screenshot_path is None

    def test_defaults_duration_seconds(self):
        result = TestResult(version="1.21.8", passed=True)
        assert result.duration_seconds is None

    def test_defaults_error(self):
        result = TestResult(version="1.21.8", passed=True)
        assert result.error is None

    def test_accepts_all_fields(self):
        result = TestResult(
            version="1.21.8",
            passed=True,
            screenshot_path="/tmp/snap.png",
            duration_seconds=12.5,
            error=None,
        )
        assert result.version == "1.21.8"
        assert result.passed is True
        assert result.screenshot_path == "/tmp/snap.png"
        assert result.duration_seconds == 12.5
        assert result.error is None


class TestJobInfo:
    """Tests for the JobInfo response model."""

    def test_defaults(self):
        from datetime import datetime, timezone
        info = JobInfo(
            job_id="job-1",
            status="finished",
            repo_url="https://github.com/test/repo.git",
            ref="main",
            owner="test",
            commit_hash="abc123",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert info.versions == []
        assert info.test_results == {}
        assert info.artifact_path is None
        assert info.error_message is None
        assert info.eta_seconds is None
        assert info.plugins == []
        assert info.login_wait_timeout == 30
