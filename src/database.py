"""SQLite database for the PicoLimbo Build API."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path("/app/builds/jobs.db")


def _ensure_db() -> None:
    """Ensure the database directory and schema exist."""
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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(repo_url, commit_hash)
            )
        """)
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
    repo_url: str, ref: str, owner: str, commit_hash: str, versions: list[str]
) -> dict:
    """Create a new job. Raises sqlite3.IntegrityError if duplicate."""
    now = _now_iso()
    job_id = _generate_job_id()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, repo_url, ref, owner, commit_hash, status, current_step, versions, test_results, error_message, eta_seconds, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'queued', NULL, ?, '[]', NULL, NULL, ?, ?)
            """,
            (job_id, repo_url, ref, owner, commit_hash, json.dumps(versions), now, now),
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


def get_job_by_key(repo_url: str, commit_hash: str) -> Optional[dict]:
    """Get an existing job by (repo_url, commit_hash) for idempotency."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE repo_url = ? AND commit_hash = ?",
            (repo_url, commit_hash),
        ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


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
    return {
        "job_id": row["job_id"],
        "status": row["status"],
        "repo_url": row["repo_url"],
        "ref": row["ref"],
        "owner": row["owner"],
        "commit_hash": row["commit_hash"],
        "artifact_path": row["artifact_path"],
        "current_step": row["current_step"],
        "versions": json.loads(row["versions"]) if row["versions"] else [],
        "test_results": (json.loads(row["test_results"]) if row["test_results"] else []) or [],
        "error_message": row["error_message"],
        "eta_seconds": row["eta_seconds"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _generate_job_id() -> str:
    """Generate a short unique job ID."""
    import secrets
    return secrets.token_hex(8)
