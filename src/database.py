"""SQLite database for the PicoLimbo Build API."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path("/app/builds/jobs.db")


def _ensure_db() -> None:
    """Ensure the database directory and schema exist.

    Adds the proxy column if the table exists but the column is missing
    (migration for existing databases).
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # Migration: add proxy column to existing tables that don't have it
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN proxy TEXT NOT NULL DEFAULT 'none'")
        except sqlite3.OperationalError:
            # Column already exists
            pass
        conn.commit()


@contextmanager
def get_connection():
    """Get a database connection with foreign keys enabled."""
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(
    repo_url: str,
    ref: str,
    owner: str,
    commit_hash: str,
    versions: list[str],
    proxy: str = "none",
) -> dict:
    """Create a new job. Raises sqlite3.IntegrityError if duplicate."""
    now = _now_iso()
    job_id = _generate_job_id()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, repo_url, ref, owner, commit_hash, status, current_step, versions, test_results, error_message, eta_seconds, proxy, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'queued', NULL, ?, '{}', NULL, NULL, ?, ?, ?)
            """,
            (job_id, repo_url, ref, owner, commit_hash, json.dumps(versions), proxy, now, now),
        )
        conn.commit()
    return get_job_by_id(job_id)


def get_job_by_id(job_id: str) -> Optional[dict]:
    """Get a job by its ID. Returns None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def get_tested_versions_for_commit(commit_hash: str) -> set[str]:
    """Get all versions that have been successfully tested (passed) across all jobs for a given commit hash.

    Only returns versions where passed == True. Failed versions are excluded so they
    can be retried by subsequent jobs.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT test_results FROM jobs WHERE commit_hash = ?",
            (commit_hash,),
        ).fetchall()
    passed: set[str] = set()
    for row in rows:
        raw = json.loads(row["test_results"]) if row["test_results"] else None
        if isinstance(raw, dict):
            for version, result in raw.items():
                if isinstance(result, dict) and result.get("passed") is True:
                    passed.add(version)
    return passed


def get_latest_test_results_for_commit(commit_hash: str) -> Optional[dict]:
    """Get the test results from the most recently completed job for a given commit hash.

    Returns a dict mapping version -> result dict, or None if no completed job exists.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT test_results FROM jobs "
            "WHERE commit_hash = ? AND status = 'finished' "
            "ORDER BY created_at DESC LIMIT 1",
            (commit_hash,),
        ).fetchone()
    if row is None:
        return None
    raw = json.loads(row["test_results"]) if row["test_results"] else None
    if not isinstance(raw, dict):
        return None
    return raw


def update_job(job_id: str, **fields) -> Optional[dict]:
    """Update job fields. Returns updated job or None if not found."""
    if not fields:
        return get_job_by_id(job_id)
    fields["updated_at"] = _now_iso()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with get_connection() as conn:
        conn.execute(
            f"UPDATE jobs SET {set_clause} WHERE job_id = ?", values
        )
        conn.commit()
    return get_job_by_id(job_id)


def get_queued_jobs(limit: int = 100) -> list[dict]:
    """Get jobs with status 'queued', ordered by creation time."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_building_jobs() -> list[dict]:
    """Get jobs with status 'building' for recovery on restart."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = 'building'"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_jobs(status: Optional[str] = None, limit: int = 100) -> list[dict]:
    """List jobs, optionally filtered by status."""
    with get_connection() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a database row to a job dict.

    The proxy column was added by schema migration; if the column
    doesn't exist (old database) we fall back to the default.
    """
    result = {
        "job_id": row["job_id"],
        "status": row["status"],
        "repo_url": row["repo_url"],
        "ref": row["ref"],
        "owner": row["owner"],
        "commit_hash": row["commit_hash"],
        "artifact_path": row["artifact_path"],
        "current_step": row["current_step"],
        "versions": json.loads(row["versions"]) if row["versions"] else [],
        "test_results": json.loads(row["test_results"]) if row["test_results"] else {},
        "error_message": row["error_message"],
        "eta_seconds": row["eta_seconds"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    # Read proxy if the column exists (added by schema migration)
    try:
        result["proxy"] = row["proxy"]
    except KeyError:
        result["proxy"] = "none"
    return result


def _generate_job_id() -> str:
    """Generate a short unique job ID."""
    import secrets
    return secrets.token_hex(8)
