"""SQLite database for the PicoLimbo Build API."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config

DB_PATH = config.DB_PATH

# Allowed column names for update_job() — prevents SQL injection
ALLOWED_UPDATE_COLUMNS: frozenset[str] = frozenset({
    "status", "artifact_path", "current_step", "versions",
    "test_results", "error_message", "eta_seconds",
    "proxy", "forwarding_method", "plugins", "login_wait_timeout",
    "created_at", "updated_at",
})


def migrate(db_path: Path | None = None) -> None:
    """Run schema migrations on the database.

    This function should be called once at application startup.
    It is idempotent — safe to call multiple times.

    Parameters
    ----------
    db_path : Path, optional
        Path to the database file. Defaults to config.DB_PATH.
    """
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        # Create the table if it doesn't exist
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
                forwarding_method TEXT NOT NULL DEFAULT 'modern',
                plugin TEXT,
                plugins TEXT,
                login_wait_timeout INTEGER NOT NULL DEFAULT 30,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # Migration: add proxy column
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN proxy TEXT NOT NULL DEFAULT 'none'")
        except sqlite3.OperationalError:
            pass
        # Migration: add forwarding_method column
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN forwarding_method TEXT NOT NULL DEFAULT 'modern'")
        except sqlite3.OperationalError:
            pass
        # Migration: add plugin column
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN plugin TEXT")
        except sqlite3.OperationalError:
            pass
        # Migration: add plugins column
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN plugins TEXT")
        except sqlite3.OperationalError:
            pass
        # Migration: add login_wait_timeout column
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN login_wait_timeout INTEGER NOT NULL DEFAULT 30")
        except sqlite3.OperationalError:
            pass
        conn.commit()


def _ensure_db() -> None:
    """Ensure the database directory and schema exist.

    Calls migrate() for schema creation, then sets up WAL mode.
    """
    migrate()


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
    forwarding_method: str = "modern",
    plugin: Optional[str] = None,
    plugins: Optional[list[str]] = None,
    login_wait_timeout: int = 30,
) -> dict:
    """Create a new job. Raises sqlite3.IntegrityError if duplicate.

    Returns the job dict with all fields populated (no second DB call).
    """
    now = _now_iso()
    job_id = _generate_job_id()
    if plugins is None and plugin is not None:
        plugins = [plugin]
    plugins_json = json.dumps(plugins) if plugins else None
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, repo_url, ref, owner, commit_hash, status, current_step, versions, test_results, error_message, eta_seconds, proxy, forwarding_method, plugins, login_wait_timeout, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'queued', NULL, ?, '{}', NULL, NULL, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, repo_url, ref, owner, commit_hash, json.dumps(versions), proxy, forwarding_method, plugins_json, login_wait_timeout, now, now),
        )
        conn.commit()
    # Return the data directly instead of re-fetching
    return {
        "job_id": job_id,
        "repo_url": repo_url,
        "ref": ref,
        "owner": owner,
        "commit_hash": commit_hash,
        "status": "queued",
        "artifact_path": None,
        "current_step": None,
        "versions": versions,
        "test_results": {},
        "error_message": None,
        "eta_seconds": None,
        "proxy": proxy,
        "forwarding_method": forwarding_method,
        "plugins": plugins or [],
        "login_wait_timeout": login_wait_timeout,
        "created_at": now,
        "updated_at": now,
    }


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
    """Update job fields. Returns updated job or None if not found.

    Raises
    ------
    ValueError
        If any field name is not an allowed column.
    """
    if not fields:
        return get_job_by_id(job_id)
    for key in fields:
        if key not in ALLOWED_UPDATE_COLUMNS:
            raise ValueError(
                f"Invalid column '{key}' for update_job. "
                f"Allowed: {sorted(ALLOWED_UPDATE_COLUMNS)}"
            )
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
    """Convert a database row to a job dict."""
    cols = row.keys()
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
        "test_results": json.loads(row["test_results"]) if row["test_results"] else {},
        "error_message": row["error_message"],
        "eta_seconds": row["eta_seconds"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "proxy": row["proxy"] if "proxy" in cols else "none",
        "forwarding_method": row["forwarding_method"] if "forwarding_method" in cols else "modern",
        "plugins": json.loads(row["plugins"]) if "plugins" in cols and row["plugins"] else [],
        "login_wait_timeout": row["login_wait_timeout"] if "login_wait_timeout" in cols else 30,
    }


def _generate_job_id() -> str:
    """Generate a short unique job ID."""
    import secrets
    return secrets.token_hex(8)
