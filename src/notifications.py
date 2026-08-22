"""In-process pub/sub hub for pushing job updates to WebSocket clients.

The hub is thread-safe: ``publish`` may be called from any thread (e.g. the
build queue worker), while subscribers are ``asyncio.Queue`` objects consumed
on the FastAPI event loop.

Every message carries the full current state of a job, so dropping stale
messages from a slow consumer never loses information.
"""

from __future__ import annotations

import asyncio
import logging
import threading

logger = logging.getLogger(__name__)


class JobEventHub:
    """Publishes job state snapshots to a set of asyncio subscriber queues."""

    def __init__(self, queue_size: int = 100) -> None:
        self._queue_size = queue_size
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue[dict[str, object]]] = set()
        self._lock = threading.Lock()

    @property
    def subscriber_count(self) -> int:
        """Number of currently subscribed queues."""
        with self._lock:
            return len(self._subscribers)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the event loop used to deliver messages.

        Called from within the event loop (e.g. on WebSocket connect).
        Safe to call multiple times; the latest loop wins.
        """
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[dict[str, object]]:
        """Create and register a subscriber queue.

        Must be called from the event loop thread.
        """
        self.bind_loop(asyncio.get_running_loop())
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(
            maxsize=self._queue_size
        )
        with self._lock:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        """Remove a subscriber queue."""
        with self._lock:
            self._subscribers.discard(queue)

    def publish(self, job: dict[str, object]) -> None:
        """Publish a job state snapshot to all subscribers.

        Thread-safe: may be called from any thread. The message is dropped
        if no event loop is bound yet (or the loop is closed), which is
        harmless because clients receive a full snapshot on connect.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        with self._lock:
            subscribers = list(self._subscribers)
        if not subscribers:
            return

        def _deliver() -> None:
            for queue in subscribers:
                try:
                    queue.put_nowait(job)
                except asyncio.QueueFull:
                    # Drop the oldest message; every message is a full
                    # snapshot so no state is lost.
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        queue.put_nowait(job)
                    except asyncio.QueueFull:
                        pass

        loop.call_soon_threadsafe(_deliver)


# Module-level singleton shared by the database layer and the API layer.
job_events = JobEventHub()
