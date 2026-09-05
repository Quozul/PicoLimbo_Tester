"""Unit tests for the schematic upload/list/delete API endpoints."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


def _make_job(job_id: str, **extra) -> dict:
    """Build a minimal job dict that satisfies the JobInfo response model."""
    now = datetime.now(timezone.utc)
    job = {
        "job_id": job_id,
        "status": "queued",
        "repo_url": "https://github.com/Quozul/PicoLimbo.git",
        "ref": "master",
        "owner": "Quozul",
        "commit_hash": "abc123",
        "current_step": None,
        "versions": [],
        "test_results": {},
        "artifact_path": None,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }
    job.update(extra)
    return job


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(mock_database, mock_engine, mock_job_runner, mock_worker, tmp_path):
    """Create a TestClient for the FastAPI app with mocked dependencies."""
    # Use temp directories for schematics and webui-dist
    tmp_schematics = tmp_path / "schematics"
    tmp_schematics.mkdir()
    tmp_webui = tmp_path / "webui-dist"
    tmp_webui.mkdir()
    tmp_assets = tmp_webui / "assets"
    tmp_assets.mkdir()

    import src.main as main_mod
    with patch.object(main_mod, "database", mock_database):
        with patch.object(main_mod, "engine", mock_engine):
            with patch.object(main_mod, "job_runner", mock_job_runner):
                with patch.object(main_mod, "worker", mock_worker):
                    with patch.object(main_mod, "config") as mock_config:
                        mock_config.SCHEMATICS_DIR = tmp_schematics
                        mock_config.WEBUI_DIR = tmp_webui
                        with TestClient(app) as c:
                            yield c


# ===========================================================================
# 1. Upload endpoint
# ===========================================================================


class TestUploadSchematic:
    def test_upload_valid_schem_file(self, client):
        """Upload a valid .schem file and check it is saved."""
        schem_content = b"fake schematic content"
        response = client.post(
            "/schematics/upload",
            files={"schematic": ("spawn.schem", schem_content, "application/octet-stream")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "spawn.schem"
        assert data["status"] == "ready"

    def test_upload_rejects_non_schem_file(self, client):
        """Upload should reject files that are not .schem files."""
        response = client.post(
            "/schematics/upload",
            files={"schematic": ("world.png", b"png content", "image/png")},
        )
        assert response.status_code == 400
        assert "Only .schem files are allowed" in response.json()["detail"]

    def test_upload_rejects_no_file(self, client):
        """Upload with no file should return 422 validation error."""
        response = client.post("/schematics/upload", data={})
        assert response.status_code == 422

    def test_upload_overwrites_existing_schem(self, client):
        """Uploading a file with an existing name should overwrite it."""
        client.post(
            "/schematics/upload",
            files={"schematic": ("spawn.schem", b"old", "application/octet-stream")},
        )
        response = client.post(
            "/schematics/upload",
            files={"schematic": ("spawn.schem", b"new", "application/octet-stream")},
        )
        assert response.status_code == 201


# ===========================================================================
# 2. List schematics endpoint
# ===========================================================================


class TestListSchematics:
    def test_list_returns_empty_when_no_schematics(self, client):
        """List schematics when no files exist should return an empty list."""
        response = client.get("/schematics")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_includes_status_ready(self, client):
        """Each schematic in the list should have status 'ready'."""
        client.post(
            "/schematics/upload",
            files={"schematic": ("spawn.schem", b"data", "application/octet-stream")},
        )
        response = client.get("/schematics")
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "spawn.schem"
        assert data[0]["status"] == "ready"

    def test_list_does_not_include_non_schem_files(self, client):
        """Non .schem files should not be listed."""
        client.post(
            "/schematics/upload",
            files={"schematic": ("spawn.schem", b"data", "application/octet-stream")},
        )
        response = client.get("/schematics")
        names = [s["name"] for s in response.json()]
        assert "notes.txt" not in names


# ===========================================================================
# 3. Delete schematic endpoint
# ===========================================================================


class TestDeleteSchematic:
    def test_delete_existing_schematic(self, client):
        """Delete an existing schematic and verify it is removed."""
        client.post(
            "/schematics/upload",
            files={"schematic": ("spawn.schem", b"data", "application/octet-stream")},
        )
        response = client.delete("/schematics/spawn.schem")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}

        response = client.get("/schematics")
        assert response.json() == []

    def test_delete_nonexistent_schematic_returns_404(self, client):
        """Deleting a schematic that does not exist should return 404."""
        response = client.delete("/schematics/missing.schem")
        assert response.status_code == 404
        assert "Schematic not found" in response.json()["detail"]

    def test_delete_multiple_schematics(self, client):
        """Delete two schematics sequentially and verify both are removed."""
        client.post(
            "/schematics/upload",
            files={"schematic": ("a.schem", b"a", "application/octet-stream")},
        )
        client.post(
            "/schematics/upload",
            files={"schematic": ("b.schem", b"b", "application/octet-stream")},
        )
        assert client.delete("/schematics/a.schem").status_code == 200
        assert client.delete("/schematics/b.schem").status_code == 200

        response = client.get("/schematics")
        assert response.json() == []


# ===========================================================================
# 4. Job creation with schematics
# ===========================================================================


class TestCreateJobWithSchematic:
    def test_job_with_existing_schematic(self, client, mock_engine):
        """A job referencing an uploaded schematic is created and the fields pass through."""
        client.post(
            "/schematics/upload",
            files={"schematic": ("spawn.schem", b"data", "application/octet-stream")},
        )
        mock_engine.create_job.return_value = _make_job(
            "job-1",
            schematic_file="spawn.schem",
            view_distance=8,
        )

        response = client.post(
            "/jobs",
            json={
                "repo_url": "https://github.com/Quozul/PicoLimbo.git",
                "schematic_file": "spawn.schem",
                "view_distance": 8,
            },
        )
        assert response.status_code == 201
        mock_engine.create_job.assert_called_once()
        kwargs = mock_engine.create_job.call_args[1]
        assert kwargs["schematic_file"] == "spawn.schem"
        assert kwargs["view_distance"] == 8

    def test_job_with_missing_schematic_returns_400(self, client, mock_engine):
        """A job referencing a schematic that was never uploaded is rejected."""
        response = client.post(
            "/jobs",
            json={
                "repo_url": "https://github.com/Quozul/PicoLimbo.git",
                "schematic_file": "nope.schem",
            },
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"]
        mock_engine.create_job.assert_not_called()

    def test_job_without_schematic_defaults_to_none(self, client, mock_engine):
        """Omitting schematic fields creates a job with disabled schematic loading."""
        mock_engine.create_job.return_value = _make_job("job-2")

        response = client.post(
            "/jobs",
            json={"repo_url": "https://github.com/Quozul/PicoLimbo.git"},
        )
        assert response.status_code == 201
        kwargs = mock_engine.create_job.call_args[1]
        assert kwargs["schematic_file"] is None
        assert kwargs["view_distance"] is None

    def test_job_with_invalid_view_distance_returns_422(self, client, mock_engine):
        """view_distance must be a positive integer."""
        response = client.post(
            "/jobs",
            json={
                "repo_url": "https://github.com/Quozul/PicoLimbo.git",
                "view_distance": 0,
            },
        )
        assert response.status_code == 422
