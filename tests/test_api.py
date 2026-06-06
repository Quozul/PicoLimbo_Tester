"""Integration tests for src/main.py FastAPI endpoints."""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(mock_database, mock_engine, mock_job_runner, mock_worker, tmp_path):
    """Create a TestClient for the FastAPI app with mocked dependencies."""
    import src.main as main_mod

    # Set up a default WEBUI_DIR with index.html for frontend tests
    webui_dir = tmp_path / "webui-dist"
    webui_dir.mkdir()
    (webui_dir / "index.html").write_text("<html></html>")

    with patch.object(main_mod, "database", mock_database):
        with patch.object(main_mod, "engine", mock_engine):
            with patch.object(main_mod, "job_runner", mock_job_runner):
                with patch.object(main_mod, "worker", mock_worker):
                    with patch.object(main_mod, "config") as mock_config:
                        mock_config.WEBUI_DIR = webui_dir
                        with TestClient(app) as c:
                            yield c
                            # Reset the mock config after each test to prevent state leakage
                            mock_config.reset_mock()


# ---------------------------------------------------------------------------
# Helpers – build a minimal job dict the way the app expects it
# ---------------------------------------------------------------------------

def _make_job(
    job_id="job-1",
    status="queued",
    repo_url="https://github.com/Quozul/PicoLimbo.git",
    ref="master",
    owner="Quozul",
    commit_hash="abc123",
    current_step=None,
    versions=None,
    test_results=None,
    artifact_path=None,
    error_message=None,
    created_at=None,
    updated_at=None,
):
    now = created_at or updated_at or datetime.now(timezone.utc)
    return {
        "job_id": job_id,
        "status": status,
        "repo_url": repo_url,
        "ref": ref,
        "owner": owner,
        "commit_hash": commit_hash,
        "current_step": current_step,
        "versions": versions or [],
        "test_results": test_results or {},
        "artifact_path": artifact_path,
        "error_message": error_message,
        "created_at": now,
        "updated_at": now,
    }


# ===========================================================================
# GET /health
# ===========================================================================

class TestHealthCheck:

    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ===========================================================================
# POST /jobs
# ===========================================================================

class TestCreateJob:

    def test_returns_201_with_job_info(self, client, mock_engine):
        job = _make_job(
            job_id="job-1",
            status="queued",
            repo_url="https://github.com/example/repo.git",
            ref="main",
        )
        mock_engine.create_job.return_value = job

        resp = client.post(
            "/jobs",
            json={
                "repo_url": "https://github.com/example/repo.git",
                "ref": "main",
                "versions": ["1.20", "1.19"],
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["job_id"] == "job-1"
        assert data["status"] == "queued"
        assert data["repo_url"] == "https://github.com/example/repo.git"
        assert data["ref"] == "main"
        assert data["owner"] == "Quozul"
        assert data["commit_hash"] == "abc123"

    def test_uses_default_values_when_body_empty(self, client, mock_engine):
        job = _make_job(job_id="job-2")
        mock_engine.create_job.return_value = job

        resp = client.post("/jobs", json={})

        assert resp.status_code == 201
        data = resp.json()
        assert data["repo_url"] == "https://github.com/Quozul/PicoLimbo.git"
        assert data["ref"] == "master"

    def test_returns_400_on_value_error(self, client, mock_engine):
        mock_engine.create_job.side_effect = ValueError("bad url")

        resp = client.post(
            "/jobs",
            json={"repo_url": "not-a-url"},
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "bad url"

    def test_returns_500_on_unexpected_exception(self, client, mock_engine):
        mock_engine.create_job.side_effect = RuntimeError("boom")

        resp = client.post(
            "/jobs",
            json={"repo_url": "https://github.com/example/repo.git"},
        )

        assert resp.status_code == 500
        assert resp.json()["detail"] == "boom"


# ===========================================================================
# GET /jobs/{job_id}
# ===========================================================================

class TestGetJob:

    def test_returns_200_with_job_info(self, client, mock_database, mock_job_runner):
        job = _make_job(
            job_id="job-1",
            status="finished",
            test_results={
                "1.20": {
                    "version": "1.20",
                    "passed": True,
                    "screenshot_path": "/tmp/snap.png",
                    "duration_seconds": 12.5,
                },
            },
        )
        mock_database.get_job_by_id.return_value = job
        mock_job_runner._compute_eta.return_value = 30

        resp = client.get("/jobs/job-1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "job-1"
        assert data["eta_seconds"] == 30
        # test_results are converted to TestResult model instances in the endpoint
        # and serialized to JSON dicts for the client
        assert "1.20" in data["test_results"]
        assert data["test_results"]["1.20"]["version"] == "1.20"
        assert data["test_results"]["1.20"]["passed"] is True

    def test_returns_404_when_job_not_found(self, client, mock_database):
        mock_database.get_job_by_id.return_value = None

        resp = client.get("/jobs/nonexistent")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Job not found"

    def test_eta_seconds_computed_when_testing(self, client, mock_database, mock_job_runner):
        job = _make_job(job_id="job-1", status="testing")
        mock_database.get_job_by_id.return_value = job
        mock_job_runner._compute_eta.return_value = 15

        resp = client.get("/jobs/job-1")

        assert resp.status_code == 200
        assert resp.json()["eta_seconds"] == 15

    def test_eta_seconds_none_when_not_testing(self, client, mock_database, mock_job_runner):
        job = _make_job(job_id="job-1", status="finished")
        mock_database.get_job_by_id.return_value = job
        mock_job_runner._compute_eta.return_value = 42

        resp = client.get("/jobs/job-1")

        assert resp.status_code == 200
        assert resp.json()["eta_seconds"] == 42


# ===========================================================================
# GET /jobs/{job_id}/artifact
# ===========================================================================

class TestGetArtifact:

    def test_returns_file_response_when_artifact_exists(self, client, mock_engine):
        # Create a real temporary file so FileResponse can stat it
        fd, tmp_path = tempfile.mkstemp(prefix="pico_limbo_")
        os.close(fd)
        try:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.__str__ = lambda s: tmp_path

            mock_engine.get_artifact_file.return_value = mock_path

            resp = client.get("/jobs/job-1/artifact")

            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/octet-stream"
        finally:
            os.unlink(tmp_path)

    def test_returns_404_when_engine_returns_none(self, client, mock_engine):
        mock_engine.get_artifact_file.return_value = None

        resp = client.get("/jobs/job-1/artifact")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Artifact not found"

    def test_returns_404_when_artifact_file_not_on_disk(self, client, mock_engine):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_path.__str__ = lambda s: "/tmp/pico_limbo"

        mock_engine.get_artifact_file.return_value = mock_path

        resp = client.get("/jobs/job-1/artifact")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Artifact file not found on disk"


# ===========================================================================
# GET /jobs/{job_id}/screenshots/{screenshot_id}
# ===========================================================================

class TestGetScreenshot:

    def test_returns_inline_image_when_screenshot_exists(self, client, mock_database):
        fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="snap_")
        os.close(fd)
        try:
            job = _make_job(
                job_id="job-1",
                status="finished",
                test_results={
                    "1.20": {
                        "version": "1.20",
                        "passed": True,
                        "screenshot_path": tmp_path,
                    },
                },
            )
            mock_database.get_job_by_id.return_value = job

            resp = client.get("/jobs/job-1/screenshots/1.20")

            assert resp.status_code == 200
            assert resp.headers["content-type"] == "image/png"
        finally:
            os.unlink(tmp_path)

    def test_returns_404_when_job_not_found(self, client, mock_database):
        mock_database.get_job_by_id.return_value = None

        resp = client.get("/jobs/nonexistent/screenshots/1.20")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Job not found"

    def test_returns_404_when_screenshot_id_not_in_test_results(self, client, mock_database):
        job = _make_job(
            job_id="job-1",
            status="finished",
            test_results={
                "1.20": {
                    "version": "1.20",
                    "passed": True,
                    "screenshot_path": "/tmp/snap.png",
                },
            },
        )
        mock_database.get_job_by_id.return_value = job

        resp = client.get("/jobs/job-1/screenshots/1.19")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Screenshot not found"

    def test_returns_404_when_screenshot_path_is_none(self, client, mock_database):
        job = _make_job(
            job_id="job-1",
            status="finished",
            test_results={
                "1.20": {
                    "version": "1.20",
                    "passed": True,
                    "screenshot_path": None,
                },
            },
        )
        mock_database.get_job_by_id.return_value = job

        resp = client.get("/jobs/job-1/screenshots/1.20")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Screenshot not found"

    def test_returns_404_when_screenshot_file_not_on_disk(self, client, mock_database):
        job = _make_job(
            job_id="job-1",
            status="finished",
            test_results={
                "1.20": {
                    "version": "1.20",
                    "passed": True,
                    "screenshot_path": "/tmp/snap.png",
                },
            },
        )
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_path.__str__ = lambda s: "/tmp/snap.png"

        mock_database.get_job_by_id.return_value = job

        with patch("pathlib.Path", return_value=mock_path):
            resp = client.get("/jobs/job-1/screenshots/1.20")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Screenshot file not found on disk"


# ===========================================================================
# GET /jobs
# ===========================================================================

class TestListJobs:

    def test_returns_200_with_list_of_jobs(self, client, mock_database, mock_job_runner):
        jobs = [
            _make_job(job_id="job-1", status="finished"),
            _make_job(job_id="job-2", status="queued"),
        ]
        mock_database.list_jobs.return_value = jobs
        mock_job_runner._compute_eta.return_value = None

        resp = client.get("/jobs")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["job_id"] == "job-1"
        assert data[1]["job_id"] == "job-2"

    def test_filters_by_status(self, client, mock_database, mock_job_runner):
        all_jobs = [
            _make_job(job_id="job-1", status="finished"),
            _make_job(job_id="job-2", status="queued"),
            _make_job(job_id="job-3", status="queued"),
        ]

        def list_jobs_side_effect(status=None, limit=100):
            result = all_jobs
            if status:
                result = [j for j in result if j["status"] == status]
            return result[:limit]

        mock_database.list_jobs.side_effect = list_jobs_side_effect
        mock_job_runner._compute_eta.return_value = None

        resp = client.get("/jobs?status=queued")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(j["status"] == "queued" for j in data)

    def test_respects_limit(self, client, mock_database, mock_job_runner):
        all_jobs = [_make_job(job_id=f"job-{i}") for i in range(10)]

        def list_jobs_side_effect(status=None, limit=100):
            return all_jobs[:limit]

        mock_database.list_jobs.side_effect = list_jobs_side_effect
        mock_job_runner._compute_eta.return_value = None

        resp = client.get("/jobs?limit=3")

        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_each_job_includes_eta_seconds(self, client, mock_database, mock_job_runner):
        jobs = [_make_job(job_id="job-1", status="testing")]
        mock_database.list_jobs.return_value = jobs
        mock_job_runner._compute_eta.return_value = 25

        resp = client.get("/jobs")

        assert resp.status_code == 200
        assert resp.json()[0]["eta_seconds"] == 25


# ===========================================================================
# POST /jobs/{job_id}/retry
# ===========================================================================

class TestRetryJob:

    def test_retries_finished_job(self, client, mock_database):
        job = _make_job(job_id="job-1", status="finished")
        updated = _make_job(job_id="job-1", status="queued", current_step=None)
        mock_database.get_job_by_id.return_value = job
        mock_database.update_job.return_value = updated

        resp = client.post("/jobs/job-1/retry")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["current_step"] is None

    def test_retries_failed_job(self, client, mock_database):
        job = _make_job(job_id="job-1", status="failed")
        updated = _make_job(job_id="job-1", status="queued", current_step=None)
        mock_database.get_job_by_id.return_value = job
        mock_database.update_job.return_value = updated

        resp = client.post("/jobs/job-1/retry")

        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    def test_returns_400_when_job_is_queued(self, client, mock_database):
        job = _make_job(job_id="job-1", status="queued")
        mock_database.get_job_by_id.return_value = job

        resp = client.post("/jobs/job-1/retry")

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Cannot retry job with status 'queued'"

    def test_returns_400_when_job_is_building(self, client, mock_database):
        job = _make_job(job_id="job-1", status="building")
        mock_database.get_job_by_id.return_value = job

        resp = client.post("/jobs/job-1/retry")

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Cannot retry job with status 'building'"

    def test_returns_400_when_job_is_testing(self, client, mock_database):
        job = _make_job(job_id="job-1", status="testing")
        mock_database.get_job_by_id.return_value = job

        resp = client.post("/jobs/job-1/retry")

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Cannot retry job with status 'testing'"

    def test_returns_404_when_job_not_found(self, client, mock_database):
        mock_database.get_job_by_id.return_value = None

        resp = client.post("/jobs/nonexistent/retry")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Job not found"


# ===========================================================================
# GET /{full_path:path} — frontend catch-all route
# ===========================================================================


class TestFrontendCatchAll:
    """Tests for the frontend catch-all route in main.py."""

    def test_serves_index_html_when_file_exists(self, client, mock_database, mock_engine, mock_job_runner, mock_worker, tmp_path):
        """When index.html exists in WEBUI_DIR, it should be served."""
        import src.main as main_mod

        # The client fixture already creates tmp_path / "webui-dist" with index.html
        # and patches config.WEBUI_DIR. The serve_frontend route reads config.WEBUI_DIR
        # at runtime, so the patched mock value is used.
        resp = client.get("/some-spa-route")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert resp.text == "<html></html>"

    def test_returns_404_when_no_index_html(self, client, mock_database, mock_engine, mock_job_runner, mock_worker, tmp_path):
        """When WEBUI_DIR has no index.html, returns 404."""
        import src.main as main_mod
        import tempfile

        # Create a fresh temp dir without index.html
        fresh_tmp = tempfile.mkdtemp()
        webui_dir = Path(fresh_tmp) / "webui-dist"
        webui_dir.mkdir()  # No index.html

        # Reset the mock config and point it to the new dir
        mock_config = main_mod.config
        mock_config.reset_mock()
        mock_config.WEBUI_DIR = webui_dir

        resp = client.get("/some-spa-route")
        assert resp.status_code == 404
        assert resp.text == "Not found"

    def test_api_routes_return_404(self, client, mock_database, mock_engine, mock_job_runner, mock_worker, tmp_path):
        """API routes should not be caught by the frontend catch-all."""
        # The client fixture already has WEBUI_DIR set up with index.html.
        # /api/health is not a registered route, so the catch-all returns 404.
        resp = client.get("/api/health")
        assert resp.status_code == 404
        # The catch-all returns a plain 404 Response (no body) for api/ paths
        assert resp.text == ""

    def test_serves_exact_file_when_exists(self, client, mock_database, mock_engine, mock_job_runner, mock_worker, tmp_path):
        """When an exact file exists in WEBUI_DIR, it should be served."""
        import src.main as main_mod

        # The /assets path is handled by StaticFiles mount (configured at module load).
        # Use a non-/assets path to test serve_frontend's exact-file serving.
        webui_dir = tmp_path / "webui-dist"
        (webui_dir / "subdir").mkdir()
        (webui_dir / "subdir" / "app.js").write_text("console.log('hello')")

        resp = client.get("/subdir/app.js")
        assert resp.status_code == 200
        assert resp.text == "console.log('hello')"
