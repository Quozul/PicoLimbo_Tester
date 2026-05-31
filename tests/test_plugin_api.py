"""Unit tests for the plugin upload/list/delete API endpoints."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Mock dependencies BEFORE importing src.main
# ---------------------------------------------------------------------------

mock_database = MagicMock()
mock_engine = MagicMock()
mock_job_runner = MagicMock()
mock_worker = MagicMock()

sys_modules_backup = {}


def _patch_modules():
    """Patch dependencies so src.main can be imported without side effects."""
    global sys_modules_backup
    sys_modules_backup = {
        "src.database": sys.modules.get("src.database"),
        "src.builder.engine": sys.modules.get("src.builder.engine"),
        "src.builder.worker": sys.modules.get("src.builder.worker"),
        "src.orchestration.job_runner": sys.modules.get("src.orchestration.job_runner"),
    }
    sys.modules["src.database"] = mock_database
    sys.modules["src.builder.engine"] = mock_engine
    sys.modules["src.builder.worker"] = mock_worker
    sys.modules["src.orchestration.job_runner"] = mock_job_runner


def _unpatch_modules():
    """Restore original modules."""
    for name, old in sys_modules_backup.items():
        if old is not None:
            sys.modules[name] = old
        else:
            sys.modules.pop(name, None)


# Create a temp directory for plugins and webui-dist so the app can start
_tmp_dir = tempfile.mkdtemp()
_TMP_PLUGINS_DIR = Path(_tmp_dir) / "plugins"
_TMP_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
_TMP_WEBUI_DIR = Path(_tmp_dir) / "webui-dist"
_TMP_WEBUI_DIR.mkdir(parents=True, exist_ok=True)
_TMP_WEBUI_ASSETS = _TMP_WEBUI_DIR / "assets"
_TMP_WEBUI_ASSETS.mkdir(parents=True, exist_ok=True)


_patch_modules()

# Import the real app (dependencies are mocked, so no side effects)
from src.main import app  # noqa: E402

_unpatch_modules()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset all mock state before each test."""
    mock_database.reset_mock()
    mock_engine.reset_mock()
    mock_job_runner.reset_mock()
    mock_worker.reset_mock()


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app with patched dependencies."""
    _patch_modules()
    # Patch the real src.main's PLUGINS_DIR and WEBUI_DIR
    if "src.main" in sys.modules:
        import src.main as main_mod
        main_mod.PLUGINS_DIR = _TMP_PLUGINS_DIR
        main_mod.WEBUI_DIR = _TMP_WEBUI_DIR
    # Ensure plugins dir is clean for this test
    for f in _TMP_PLUGINS_DIR.glob("*.jar"):
        f.unlink()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        _unpatch_modules()


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


# ===========================================================================
# 5. Database plugin column
# ===========================================================================


class TestDatabasePluginColumn:
    def _setup_inmemory_db(self):
        """Set up an in-memory test database like test_database.py does."""
        import contextlib
        import sqlite3
        import src.database as db

        class _ConnHolder:
            conn: sqlite3.Connection | None = None

        _ConnHolder.conn = sqlite3.connect(":memory:")
        _ConnHolder.conn.row_factory = sqlite3.Row
        _ConnHolder.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                repo_url TEXT NOT NULL,
                ref TEXT NOT NULL,
                owner TEXT NOT NULL,
                commit_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                artifact_path TEXT,
                current_step TEXT,
                versions TEXT,
                test_results TEXT,
                error_message TEXT,
                eta_seconds INTEGER,
                proxy TEXT NOT NULL DEFAULT 'none',
                forwarding_method TEXT NOT NULL DEFAULT 'modern',
                plugin TEXT,
                plugins TEXT,
                login_wait_timeout INTEGER NOT NULL DEFAULT 30,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        _ConnHolder.conn.commit()

        @contextlib.contextmanager
        def fake_get_connection():
            yield _ConnHolder.conn

        self._patcher_db_path = __import__("unittest.mock").mock.patch.object(
            db, "DB_PATH", ":memory:"
        )
        self._patcher_ensure = __import__("unittest.mock").mock.patch.object(
            db, "_ensure_db", lambda: None
        )
        self._patcher_conn = __import__("unittest.mock").mock.patch.object(
            db, "get_connection", fake_get_connection
        )
        self._patcher_db_path.start()
        self._patcher_ensure.start()
        self._patcher_conn.start()

    def _teardown_inmemory_db(self):
        self._patcher_db_path.stop()
        self._patcher_ensure.stop()
        self._patcher_conn.stop()

    def test_create_job_with_plugins(self):
        """Creating a job should persist the plugins field."""
        import src.database as db

        self._setup_inmemory_db()
        try:
            job = db.create_job(
                repo_url="https://github.com/owner/repo.git",
                ref="main",
                owner="owner",
                commit_hash="a" * 40,
                versions=["1.20"],
                proxy="velocity",
                forwarding_method="modern",
                plugins=["my-plugin.jar"],
            )
            assert job["plugins"] == ["my-plugin.jar"]
        finally:
            self._teardown_inmemory_db()

    def test_create_job_with_legacy_single_plugin(self):
        """Passing legacy plugin param should convert to plugins list."""
        import src.database as db

        self._setup_inmemory_db()
        try:
            job = db.create_job(
                repo_url="https://github.com/owner/repo.git",
                ref="main",
                owner="owner",
                commit_hash="a" * 40,
                versions=["1.20"],
                proxy="velocity",
                forwarding_method="modern",
                plugin="legacy-plugin.jar",
            )
            assert job["plugins"] == ["legacy-plugin.jar"]
        finally:
            self._teardown_inmemory_db()

    def test_create_job_without_plugins(self):
        """Creating a job without plugins should store empty list."""
        import src.database as db

        self._setup_inmemory_db()
        try:
            job = db.create_job(
                repo_url="https://github.com/owner/repo.git",
                ref="main",
                owner="owner",
                commit_hash="b" * 40,
                versions=["1.20"],
            )
            assert job["plugins"] == []
        finally:
            self._teardown_inmemory_db()

    def test_get_job_returns_plugins(self):
        """Retrieving a job should include the plugins field."""
        import src.database as db

        self._setup_inmemory_db()
        try:
            job = db.create_job(
                repo_url="https://github.com/owner/repo.git",
                ref="main",
                owner="owner",
                commit_hash="c" * 40,
                versions=["1.21"],
                proxy="velocity",
                plugins=["test.jar", "another.jar"],
            )
            fetched = db.get_job_by_id(job["job_id"])
            assert fetched["plugins"] == ["test.jar", "another.jar"]
        finally:
            self._teardown_inmemory_db()


# ===========================================================================
# 6. Engine plugin parameter
# ===========================================================================


class TestEnginePluginParameter:
    def test_create_job_passes_plugins_to_database(self):
        """engine.create_job should forward the plugins parameter."""
        from src.builder import engine
        from unittest.mock import patch

        mock_job = {"job_id": "test123", "status": "queued"}

        with patch.object(engine, "extract_owner_from_url", return_value=("Quozul", "PicoLimbo")):
            with patch.object(engine, "ensure_repo_cloned"):
                with patch.object(engine, "resolve_commit", return_value="a" * 40):
                    with patch.object(engine.database, "create_job", return_value=mock_job) as mock_db:
                        engine.create_job(
                            repo_url="https://github.com/Quozul/PicoLimbo.git",
                            ref="main",
                            proxy="velocity",
                            plugins=["my-plugin.jar"],
                        )
                        mock_db.assert_called_once_with(
                            "https://github.com/Quozul/PicoLimbo.git",
                            "main", "Quozul", "a" * 40,
                            [], "velocity", "modern", None, ["my-plugin.jar"], 30,
                        )

    def test_create_job_without_plugins(self):
        """engine.create_job without plugins should pass None for both."""
        from src.builder import engine
        from unittest.mock import patch

        mock_job = {"job_id": "test123", "status": "queued"}

        with patch.object(engine, "extract_owner_from_url", return_value=("Quozul", "PicoLimbo")):
            with patch.object(engine, "ensure_repo_cloned"):
                with patch.object(engine, "resolve_commit", return_value="a" * 40):
                    with patch.object(engine.database, "create_job", return_value=mock_job) as mock_db:
                        engine.create_job(
                            repo_url="https://github.com/Quozul/PicoLimbo.git",
                            ref="main",
                        )
                        args = mock_db.call_args[0]
                        assert args[7] is None  # plugin (legacy)
                        assert args[8] is None  # plugins
