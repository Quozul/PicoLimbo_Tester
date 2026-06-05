"""Unit tests for the plugin upload/list/delete API endpoints."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(mock_database, mock_engine, mock_job_runner, mock_worker, tmp_path):
    """Create a TestClient for the FastAPI app with mocked dependencies."""
    # Use a temp directory for plugins and webui-dist
    tmp_plugins = tmp_path / "plugins"
    tmp_plugins.mkdir()
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
                        mock_config.PLUGINS_DIR = tmp_plugins
                        mock_config.WEBUI_DIR = tmp_webui
                        with TestClient(app) as c:
                            yield c


# ===========================================================================
# 1. Upload endpoint
# ===========================================================================


class TestUploadPlugin:
    def test_upload_valid_jar_file(self, client):
        """Upload a valid .jar file and check it is saved."""
        jar_content = b"fake jar content"
        response = client.post(
            "/plugins/upload",
            files={"plugin": ("test-plugin.jar", jar_content, "application/java-archive")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-plugin.jar"
        assert data["status"] == "ready"

    def test_upload_rejects_non_jar_file(self, client):
        """Upload should reject files that are not .jar files."""
        response = client.post(
            "/plugins/upload",
            files={"plugin": ("test.zip", b"zip content", "application/zip")},
        )
        assert response.status_code == 400
        assert "Only .jar files are allowed" in response.json()["detail"]

    def test_upload_rejects_no_file(self, client):
        """Upload with no file should return 422 validation error."""
        response = client.post("/plugins/upload", data={})
        assert response.status_code == 422

    def test_upload_overwrites_existing_jar(self, client):
        """Uploading a file with an existing name should overwrite it."""
        old_content = b"old content"
        new_content = b"new content"

        # Upload the old version first
        client.post(
            "/plugins/upload",
            files={"plugin": ("overwritten.jar", old_content, "application/java-archive")},
        )

        # Upload the new version with same name
        response = client.post(
            "/plugins/upload",
            files={"plugin": ("overwritten.jar", new_content, "application/java-archive")},
        )
        assert response.status_code == 201


# ===========================================================================
# 2. List plugins endpoint
# ===========================================================================


class TestListPlugins:
    def test_list_returns_empty_when_no_plugins(self, client):
        """List plugins when no files exist should return an empty list."""
        response = client.get("/plugins")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_includes_status_ready(self, client):
        """Each plugin in the list should have status 'ready'."""
        # Create a fake jar file via the upload endpoint
        client.post(
            "/plugins/upload",
            files={"plugin": ("test.jar", b"data", "application/java-archive")},
        )
        response = client.get("/plugins")
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "ready"

    def test_list_does_not_include_non_jar_files(self, client):
        """Non .jar files should not be listed."""
        response = client.get("/plugins")
        data = response.json()
        names = [p["name"] for p in data]
        assert "other.txt" not in names


# ===========================================================================
# 3. Delete plugin endpoint
# ===========================================================================


class TestDeletePlugin:
    def test_delete_existing_plugin(self, client):
        """Delete an existing plugin and verify it is removed."""
        # First upload a plugin
        client.post(
            "/plugins/upload",
            files={"plugin": ("plugin.jar", b"data", "application/java-archive")},
        )
        response = client.delete("/plugins/plugin.jar")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}

        # Verify it's gone from the list
        response = client.get("/plugins")
        assert response.json() == []

    def test_delete_nonexistent_plugin_returns_404(self, client):
        """Deleting a plugin that does not exist should return 404."""
        response = client.delete("/plugins/missing.jar")
        assert response.status_code == 404
        assert "Plugin not found" in response.json()["detail"]

    def test_delete_multiple_plugins(self, client):
        """Delete two plugins sequentially and verify both are removed."""
        client.post(
            "/plugins/upload",
            files={"plugin": ("a.jar", b"a", "application/java-archive")},
        )
        client.post(
            "/plugins/upload",
            files={"plugin": ("b.jar", b"b", "application/java-archive")},
        )
        resp1 = client.delete("/plugins/a.jar")
        assert resp1.status_code == 200
        resp2 = client.delete("/plugins/b.jar")
        assert resp2.status_code == 200

        response = client.get("/plugins")
        assert response.json() == []


# ===========================================================================
# 4. Plugin model validation
# ===========================================================================


class TestPluginModel:
    def test_job_create_accepts_plugins_field(self):
        """JobCreate model should accept an optional plugins field."""
        from src.models import JobCreate

        job = JobCreate(plugins=["my-plugin.jar"])
        assert job.plugins == ["my-plugin.jar"]

    def test_job_create_defaults_plugins_to_none(self):
        """JobCreate should default plugins to None when not provided."""
        from src.models import JobCreate

        job = JobCreate()
        assert job.plugins is None
