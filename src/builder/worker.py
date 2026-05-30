"""Build queue worker with single-worker guarantee."""

import logging
import threading
from typing import Optional

from . import database
from . import engine
from ..orchestration import job_runner

logger = logging.getLogger(__name__)

# Lock to ensure only one build runs at a time
_build_lock = threading.Lock()


def _process_queue() -> None:
    """Background worker: process queued jobs one at a time."""
    logger.info("Build queue worker started")
    while True:
        # Get next queued job
        jobs = database.get_queued_jobs(limit=1)
        if not jobs:
            # No queued jobs, wait a bit
            threading.Event().wait(2)
            continue

        job = jobs[0]
        job_id = job["job_id"]

        # Acquire lock (ensures single build at a time)
        with _build_lock:
            # Re-read job to check it's still queued (might have been taken)
            current = database.get_job_by_id(job_id)
            if not current or current["status"] != "queued":
                continue

            logger.info("Processing job %s", job_id)
            # Delegate to orchestrator for full lifecycle
            job_runner.run_job(job_id)


def recover_stuck_jobs() -> None:
    """On startup, recover jobs stuck in 'building' state."""
    building = database.get_building_jobs()
    for job in building:
        artifact_path = job.get("artifact_path")
        if artifact_path and __import__("pathlib").Path(artifact_path).exists():
            logger.info("Recovering job %s: artifact exists, marking finished", job["job_id"])
            database.update_job(job["job_id"], status="finished")
        else:
            logger.info("Recovering job %s: re-queuing", job["job_id"])
            database.update_job(job["job_id"], status="queued")


def start_queue_worker() -> threading.Thread:
    """Start the background queue worker thread. Returns the thread."""
    recover_stuck_jobs()
    t = threading.Thread(target=_process_queue, daemon=True, name="build-worker")
    t.start()
    return t
