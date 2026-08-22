"""Unit tests for src/notifications.py — the job event hub."""

import asyncio
import threading

from src.notifications import JobEventHub


def _run(coro) -> None:
    asyncio.run(asyncio.wait_for(coro, timeout=2))


def test_publish_delivers_job_to_subscriber():
    async def scenario():
        hub = JobEventHub()
        queue = hub.subscribe()
        hub.publish({"job_id": "abc", "status": "building"})
        job = await queue.get()
        assert job == {"job_id": "abc", "status": "building"}
        hub.unsubscribe(queue)

    _run(scenario())


def test_subscribe_increments_subscriber_count():
    async def scenario():
        hub = JobEventHub()
        assert hub.subscriber_count == 0
        queue = hub.subscribe()
        assert hub.subscriber_count == 1
        hub.unsubscribe(queue)
        assert hub.subscriber_count == 0

    _run(scenario())


def test_unsubscribe_stops_delivery():
    async def scenario():
        hub = JobEventHub()
        queue = hub.subscribe()
        hub.unsubscribe(queue)
        hub.publish({"job_id": "abc"})
        await asyncio.sleep(0.05)
        assert queue.empty()

    _run(scenario())


def test_publish_with_no_subscribers_is_noop():
    async def scenario():
        hub = JobEventHub()
        hub.publish({"job_id": "abc"})  # must not raise
        await asyncio.sleep(0.05)

    _run(scenario())


def test_publish_before_any_loop_bind_is_noop():
    hub = JobEventHub()
    hub.publish({"job_id": "abc"})  # must not raise (no loop bound)


def test_publish_after_loop_closed_is_noop():
    hub = JobEventHub()

    async def scenario():
        hub.subscribe()

    _run(scenario())
    hub.publish({"job_id": "abc"})  # loop is closed, must not raise


def test_publish_from_background_thread():
    """publish() must be callable from a non-event-loop thread."""
    hub = JobEventHub()
    ready = threading.Event()
    received: list[dict] = []

    async def scenario():
        queue = hub.subscribe()
        ready.set()
        received.append(await asyncio.wait_for(queue.get(), timeout=2))
        hub.unsubscribe(queue)

    thread = threading.Thread(target=lambda: asyncio.run(scenario()))
    thread.start()
    try:
        assert ready.wait(timeout=2)
        hub.publish({"job_id": "xyz", "status": "testing"})
        thread.join(timeout=3)
    finally:
        thread.join(timeout=3)

    assert not thread.is_alive()
    assert received == [{"job_id": "xyz", "status": "testing"}]


def test_full_queue_drops_oldest_message():
    """Every message is a full snapshot, so a slow consumer may drop stale ones."""

    async def scenario():
        hub = JobEventHub(queue_size=2)
        queue = hub.subscribe()
        hub.publish({"job_id": "1"})
        hub.publish({"job_id": "2"})
        hub.publish({"job_id": "3"})
        await asyncio.sleep(0.05)
        first = await queue.get()
        second = await queue.get()
        assert first["job_id"] == "2"
        assert second["job_id"] == "3"
        assert queue.empty()
        hub.unsubscribe(queue)

    _run(scenario())


def test_multiple_subscribers_all_receive_job():
    async def scenario():
        hub = JobEventHub()
        q1 = hub.subscribe()
        q2 = hub.subscribe()
        hub.publish({"job_id": "abc"})
        await asyncio.sleep(0.05)
        assert await q1.get() == {"job_id": "abc"}
        assert await q2.get() == {"job_id": "abc"}
        hub.unsubscribe(q1)
        hub.unsubscribe(q2)

    _run(scenario())
