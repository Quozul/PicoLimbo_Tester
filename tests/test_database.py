"""Unit tests for src/database.py"""

import contextlib
import json
import sqlite3
import time
from datetime import datetime
from unittest.mock import patch

import pytest

import src.database as db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_test_db(conn: sqlite3.Connection) -> None:
    """Create the jobs table in the given connection."""
    conn.execute(
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
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


# Module-level holder so nested closures always reference the same object.
class _ConnHolder:
    conn: sqlite3.Connection | None = None


@pytest.fixture
def patched_db():
    """Patch DB_PATH, _ensure_db, and get_connection to use an in-memory DB.

    Each test gets its own isolated in-memory database via a shared connection.
    """
    _ConnHolder.conn = sqlite3.connect(":memory:")
    _ConnHolder.conn.row_factory = sqlite3.Row
    _setup_test_db(_ConnHolder.conn)

    @contextlib.contextmanager
    def fake_get_connection():
        yield _ConnHolder.conn

    with patch.object(db, "DB_PATH", ":memory:"):
        with patch.object(db, "_ensure_db", lambda: None):
            with patch.object(db, "get_connection", fake_get_connection):
                yield ":memory:"


# ---------------------------------------------------------------------------
# 1. create_job
# ---------------------------------------------------------------------------

class TestCreateJob:
    def test_creates_job_with_all_fields(self, patched_db):
        result = db.create_job(
            repo_url="https://github.com/foo/bar",
            ref="main",
            owner="foo",
            commit_hash="abc123def456",
            versions=["3.10", "3.11"],
        )
        assert result["job_id"] is not None
        assert len(result["job_id"]) == 16
        int(result["job_id"], 16)
        assert result["repo_url"] == "https://github.com/foo/bar"
        assert result["ref"] == "main"
        assert result["owner"] == "foo"
        assert result["commit_hash"] == "abc123def456"
        assert result["status"] == "queued"
        assert result["versions"] == ["3.10", "3.11"]
        assert result["test_results"] == {}
        assert result["artifact_path"] is None
        assert result["error_message"] is None
        assert result["current_step"] is None
        assert result["eta_seconds"] is None

    def test_created_at_and_updated_at_are_valid_iso(self, patched_db):
        result = db.create_job(
            repo_url="https://github.com/foo/bar",
            ref="main",
            owner="foo",
            commit_hash="abc123",
            versions=["3.10"],
        )
        datetime.fromisoformat(result["created_at"])
        datetime.fromisoformat(result["updated_at"])

    def test_duplicate_job_id_raises_integrity_error(self, patched_db):
        """Calling create_job with a pre-existing job_id should raise."""
        fixed_id = "deadbeef12345678"
        now = db._now_iso()
        with db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (job_id, repo_url, ref, owner, commit_hash, status,
                    current_step, versions, test_results, error_message, eta_seconds,
                    created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'queued', NULL, ?, '{}', NULL, NULL, ?, ?)
                """,
                (fixed_id, "https://github.com/x/y", "main", "x",
                 "abc123", json.dumps(["3.10"]), now, now),
            )
            conn.commit()

        with patch.object(db, "_generate_job_id", return_value=fixed_id):
            with pytest.raises(sqlite3.IntegrityError):
                db.create_job(
                    repo_url="https://github.com/x/y",
                    ref="main",
                    owner="x",
                    commit_hash="abc123",
                    versions=["3.10"],
                )

    def test_returns_job_by_id_after_creation(self, patched_db):
        result = db.create_job(
            repo_url="https://github.com/foo/bar",
            ref="develop",
            owner="foo",
            commit_hash="deadbeef",
            versions=["3.11"],
        )
        fetched = db.get_job_by_id(result["job_id"])
        assert fetched is not None
        assert fetched["job_id"] == result["job_id"]


# ---------------------------------------------------------------------------
# 2. get_job_by_id
# ---------------------------------------------------------------------------

class TestGetJobById:
    def test_returns_none_for_nonexistent_id(self, patched_db):
        result = db.get_job_by_id("nonexistent12345678")
        assert result is None

    def test_returns_created_job(self, patched_db):
        created = db.create_job(
            repo_url="https://github.com/foo/bar",
            ref="main",
            owner="foo",
            commit_hash="abc123",
            versions=["3.10"],
        )
        fetched = db.get_job_by_id(created["job_id"])
        assert fetched is not None
        assert fetched["job_id"] == created["job_id"]
        assert fetched["repo_url"] == "https://github.com/foo/bar"


# ---------------------------------------------------------------------------
# 3. update_job
# ---------------------------------------------------------------------------

class TestUpdateJob:
    def test_updates_specified_fields(self, patched_db):
        created = db.create_job(
            repo_url="https://github.com/foo/bar",
            ref="main",
            owner="foo",
            commit_hash="abc123",
            versions=["3.10"],
        )
        updated = db.update_job(
            created["job_id"],
            status="building",
            artifact_path="/tmp/artifact.tar",
        )
        assert updated["status"] == "building"
        assert updated["artifact_path"] == "/tmp/artifact.tar"

    def test_updated_at_refreshes(self, patched_db):
        created = db.create_job(
            repo_url="https://github.com/foo/bar",
            ref="main",
            owner="foo",
            commit_hash="abc123",
            versions=["3.10"],
        )
        old_updated = created["updated_at"]
        time.sleep(0.05)
        updated = db.update_job(created["job_id"], status="building")
        assert updated["updated_at"] != old_updated
        datetime.fromisoformat(updated["updated_at"])

    def test_returns_none_for_nonexistent_id(self, patched_db):
        result = db.update_job("nonexistent12345678", status="finished")
        assert result is None

    def test_no_fields_returns_job_unchanged(self, patched_db):
        created = db.create_job(
            repo_url="https://github.com/foo/bar",
            ref="main",
            owner="foo",
            commit_hash="abc123",
            versions=["3.10"],
        )
        returned = db.update_job(created["job_id"])
        assert returned["status"] == created["status"]
        assert returned["repo_url"] == created["repo_url"]
        assert returned["versions"] == created["versions"]

    def test_updates_test_results(self, patched_db):
        created = db.create_job(
            repo_url="https://github.com/foo/bar",
            ref="main",
            owner="foo",
            commit_hash="abc123",
            versions=["3.10", "3.11"],
        )
        # update_job does NOT json-serialize test_results, so we pass a JSON string.
        test_results_json = json.dumps(
            {"3.10": {"passed": True}, "3.11": {"passed": False}}
        )
        updated = db.update_job(created["job_id"], test_results=test_results_json)
        assert updated["test_results"] == {"3.10": {"passed": True}, "3.11": {"passed": False}}


# ---------------------------------------------------------------------------
# 4. list_jobs
# ---------------------------------------------------------------------------

class TestListJobs:
    def test_returns_all_jobs_when_no_filter(self, patched_db):
        db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="aaaa1111", versions=["3.10"],
        )
        db.create_job(
            repo_url="https://github.com/c/d", ref="dev", owner="c",
            commit_hash="bbbb2222", versions=["3.11"],
        )
        jobs = db.list_jobs()
        assert len(jobs) == 2

    def test_filters_by_status(self, patched_db):
        db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="aaaa1111", versions=["3.10"],
        )
        db.create_job(
            repo_url="https://github.com/c/d", ref="dev", owner="c",
            commit_hash="bbbb2222", versions=["3.11"],
        )
        all_jobs = db.list_jobs()
        db.update_job(all_jobs[0]["job_id"], status="finished")

        queued = db.list_jobs(status="queued")
        finished = db.list_jobs(status="finished")
        assert len(queued) == 1
        assert queued[0]["status"] == "queued"
        assert len(finished) == 1
        assert finished[0]["status"] == "finished"

    def test_respects_limit(self, patched_db):
        for i in range(5):
            db.create_job(
                repo_url="https://github.com/a/b", ref="main", owner="a",
                commit_hash=f"hash{i:04d}", versions=["3.10"],
            )
        jobs = db.list_jobs(limit=3)
        assert len(jobs) == 3

    def test_results_ordered_by_created_at_desc(self, patched_db):
        for i in range(3):
            db.create_job(
                repo_url="https://github.com/a/b", ref="main", owner="a",
                commit_hash=f"hash{i:04d}", versions=["3.10"],
            )
            time.sleep(0.01)
        listed = db.list_jobs()
        assert len(listed) == 3
        assert listed[0]["commit_hash"] == "hash0002"
        assert listed[2]["commit_hash"] == "hash0000"


# ---------------------------------------------------------------------------
# 5. get_queued_jobs
# ---------------------------------------------------------------------------

class TestGetQueuedJobs:
    def test_returns_only_queued_jobs(self, patched_db):
        db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="aaaa1111", versions=["3.10"],
        )
        db.create_job(
            repo_url="https://github.com/c/d", ref="dev", owner="c",
            commit_hash="bbbb2222", versions=["3.11"],
        )
        all_jobs = db.list_jobs()
        db.update_job(all_jobs[0]["job_id"], status="finished")

        queued = db.get_queued_jobs()
        assert len(queued) == 1
        assert queued[0]["status"] == "queued"

    def test_respects_limit(self, patched_db):
        for i in range(5):
            db.create_job(
                repo_url="https://github.com/a/b", ref="main", owner="a",
                commit_hash=f"hash{i:04d}", versions=["3.10"],
            )
        queued = db.get_queued_jobs(limit=2)
        assert len(queued) == 2

    def test_returns_empty_list_when_no_queued_jobs(self, patched_db):
        db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="aaaa1111", versions=["3.10"],
        )
        all_jobs = db.list_jobs()
        db.update_job(all_jobs[0]["job_id"], status="finished")
        assert db.get_queued_jobs() == []


# ---------------------------------------------------------------------------
# 6. get_tested_versions_for_commit
# ---------------------------------------------------------------------------

class TestGetTestedVersionsForCommit:
    def test_returns_passed_versions(self, patched_db):
        job = db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="abc123", versions=["3.10", "3.11", "3.12"],
        )
        db.update_job(
            job["job_id"], status="finished",
            test_results=json.dumps({
                "3.10": {"passed": True},
                "3.11": {"passed": False},
                "3.12": {"passed": True},
            }),
        )
        passed = db.get_tested_versions_for_commit("abc123")
        assert passed == {"3.10", "3.12"}

    def test_excludes_failed_versions(self, patched_db):
        job = db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="abc123", versions=["3.10", "3.11"],
        )
        db.update_job(
            job["job_id"], status="finished",
            test_results=json.dumps({
                "3.10": {"passed": True},
                "3.11": {"passed": False},
            }),
        )
        passed = db.get_tested_versions_for_commit("abc123")
        assert "3.11" not in passed
        assert "3.10" in passed

    def test_returns_empty_set_when_no_jobs(self, patched_db):
        assert db.get_tested_versions_for_commit("nonexistent") == set()

    def test_aggregates_across_multiple_jobs(self, patched_db):
        job1 = db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="abc123", versions=["3.10"],
        )
        db.update_job(
            job1["job_id"], status="finished",
            test_results=json.dumps({"3.10": {"passed": True}}),
        )
        job2 = db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="abc123", versions=["3.11"],
        )
        db.update_job(
            job2["job_id"], status="finished",
            test_results=json.dumps({"3.11": {"passed": True}}),
        )
        passed = db.get_tested_versions_for_commit("abc123")
        assert passed == {"3.10", "3.11"}

    def test_empty_test_results_returns_empty_set(self, patched_db):
        db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="abc123", versions=["3.10"],
        )
        assert db.get_tested_versions_for_commit("abc123") == set()


# ---------------------------------------------------------------------------
# 7. get_latest_test_results_for_commit
# ---------------------------------------------------------------------------

class TestGetLatestTestResultsForCommit:
    def test_returns_results_from_latest_finished_job(self, patched_db):
        job1 = db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="abc123", versions=["3.10"],
        )
        db.update_job(
            job1["job_id"], status="finished",
            test_results=json.dumps({"3.10": {"passed": False}}),
        )
        time.sleep(0.01)

        job2 = db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="abc123", versions=["3.10"],
        )
        db.update_job(
            job2["job_id"], status="finished",
            test_results=json.dumps({"3.10": {"passed": True}}),
        )

        results = db.get_latest_test_results_for_commit("abc123")
        assert results == {"3.10": {"passed": True}}

    def test_returns_none_when_no_finished_job(self, patched_db):
        db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="abc123", versions=["3.10"],
        )
        assert db.get_latest_test_results_for_commit("abc123") is None

    def test_returns_none_when_no_jobs_exist(self, patched_db):
        assert db.get_latest_test_results_for_commit("nonexistent") is None

    def test_skips_non_finished_jobs(self, patched_db):
        db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="abc123", versions=["3.10"],
        )
        assert db.get_latest_test_results_for_commit("abc123") is None


# ---------------------------------------------------------------------------
# 8. get_building_jobs
# ---------------------------------------------------------------------------

class TestGetBuildingJobs:
    def test_returns_only_building_jobs(self, patched_db):
        db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="aaaa1111", versions=["3.10"],
        )
        db.create_job(
            repo_url="https://github.com/c/d", ref="dev", owner="c",
            commit_hash="bbbb2222", versions=["3.11"],
        )
        all_jobs = db.list_jobs()
        db.update_job(all_jobs[0]["job_id"], status="building")

        building = db.get_building_jobs()
        assert len(building) == 1
        assert building[0]["status"] == "building"

    def test_returns_empty_list_when_no_building_jobs(self, patched_db):
        db.create_job(
            repo_url="https://github.com/a/b", ref="main", owner="a",
            commit_hash="aaaa1111", versions=["3.10"],
        )
        assert db.get_building_jobs() == []

    def test_all_queued_jobs_excluded(self, patched_db):
        for i in range(3):
            db.create_job(
                repo_url="https://github.com/a/b", ref="main", owner="a",
                commit_hash=f"hash{i:04d}", versions=["3.10"],
            )
        assert db.get_building_jobs() == []
