"""Pytest configuration — sys.path setup and shared DI fixtures."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure src/ is on sys.path for all tests
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def reset_di():
    """Reset DI module instances before each test."""
    from src import di
    di.reset()
    yield


@pytest.fixture
def mock_database():
    """Provide a mock database module."""
    db = MagicMock()
    # Set up default return values
    db.get_job_by_id.return_value = None
    db.list_jobs.return_value = []
    db.get_queued_jobs.return_value = []
    db.get_building_jobs.return_value = []
    db.create_job.return_value = {"job_id": "test-job", "status": "queued"}
    db.update_job.return_value = None
    yield db


@pytest.fixture
def mock_engine():
    """Provide a mock engine module."""
    eng = MagicMock()
    eng.create_job.return_value = {
        "job_id": "test-job",
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
        "created_at": None,
        "updated_at": None,
    }
    eng.get_artifact_file.return_value = None
    yield eng


@pytest.fixture
def mock_job_runner():
    """Provide a mock job_runner module."""
    jr = MagicMock()
    jr._compute_eta.return_value = None
    jr.run_job.return_value = None
    yield jr


@pytest.fixture
def mock_worker():
    """Provide a mock worker module."""
    w = MagicMock()
    w.start_queue_worker.return_value = None
    yield w
