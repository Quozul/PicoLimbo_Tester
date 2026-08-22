"""End-to-end tests for /ws/jobs using the real database layer.

Verifies the full push chain: database write -> notifications hub ->
WebSocket message.
"""

import threading

import pytest
from fastapi.testclient import TestClient

import src.database as database
from src.orchestration import job_runner


@pytest.fixture
def ws_client(tmp_path, monkeypatch, mock_worker):
    """TestClient with a real (temporary) database and a stubbed queue worker."""
    import src.main as main_mod

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(job_runner, "_compute_eta", lambda job: None)
    monkeypatch.setattr(main_mod, "worker", mock_worker)
    with TestClient(main_mod.app) as client:
        yield client


def _receive_json(ws, timeout=10.0):
    """Receive a JSON message, failing the test if the server stops sending."""
    box: dict = {}

    def _worker():
        try:
            box["message"] = ws.receive_json()
        except BaseException as exc:
            box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        pytest.fail(f"Timed out after {timeout}s waiting for a WebSocket message")
    if "error" in box:
        raise box["error"]
    return box["message"]


def _create_job(**overrides) -> dict:
    kwargs = dict(
        repo_url="https://github.com/foo/bar",
        ref="main",
        owner="foo",
        commit_hash="a" * 40,
        versions=["1.20"],
    )
    kwargs.update(overrides)
    return database.create_job(**kwargs)


def test_job_update_pushed_after_db_write(ws_client):
    job = _create_job()

    with ws_client.websocket_connect("/ws/jobs") as ws:
        snapshot = _receive_json(ws)
        assert snapshot["type"] == "snapshot"
        assert [j["job_id"] for j in snapshot["jobs"]] == [job["job_id"]]
        assert snapshot["jobs"][0]["status"] == "queued"

        database.update_job(
            job["job_id"], status="building", current_step="building"
        )
        message = _receive_json(ws)

    assert message["type"] == "job_update"
    assert message["job"]["job_id"] == job["job_id"]
    assert message["job"]["status"] == "building"
    assert message["job"]["current_step"] == "building"


def test_create_job_pushed_to_already_connected_client(ws_client):
    with ws_client.websocket_connect("/ws/jobs") as ws:
        snapshot = _receive_json(ws)
        assert snapshot["type"] == "snapshot"
        assert snapshot["jobs"] == []

        job = _create_job(commit_hash="b" * 40)
        message = _receive_json(ws)

    assert message["type"] == "job_update"
    assert message["job"]["job_id"] == job["job_id"]
    assert message["job"]["status"] == "queued"


def test_test_results_included_in_pushed_updates(ws_client):
    job = _create_job(versions=["1.20", "1.19"])

    with ws_client.websocket_connect("/ws/jobs") as ws:
        _receive_json(ws)  # snapshot

        database.update_job(
            job["job_id"],
            status="testing",
            test_results=(
                '{"1.20": {"version": "1.20", "passed": true, '
                '"screenshot_path": "/tmp/s.png", "duration_seconds": 10.0}}'
            ),
        )
        message = _receive_json(ws)

    result = message["job"]["test_results"]["1.20"]
    assert result["passed"] is True
    assert result["screenshot_path"] == "/tmp/s.png"


def test_retry_pushes_status_change(ws_client):
    job = _create_job(commit_hash="c" * 40)
    database.update_job(job["job_id"], status="finished")

    with ws_client.websocket_connect("/ws/jobs") as ws:
        snapshot = _receive_json(ws)
        assert snapshot["jobs"][0]["status"] == "finished"

        database.update_job(job["job_id"], status="queued", current_step=None)
        message = _receive_json(ws)

    assert message["type"] == "job_update"
    assert message["job"]["status"] == "queued"
    assert message["job"]["current_step"] is None
