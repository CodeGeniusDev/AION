"""Phase 2B: Real-time SSE Hub tests.

Covers the six contract points the spec requires:
1. Ordering — events are delivered in publish order per tenant.
2. Last-Event-ID resume — a reconnecting client receives buffered events
   after the given ID, or a resync signal when the window has expired.
3. Tenant isolation — a subscriber only receives events for its tenant.
4. Redaction — approval events never carry parameters, secrets or tokens.
5. Backpressure — a slow client whose queue is full drops the oldest event
   and receives a resync signal.
6. Hub failure isolation — a broken hub NEVER blocks or alters an approval.

Tests use synchronous wrappers around asyncio.run() to avoid adding
pytest-asyncio (the directive prohibits new deps unless justified; the
hub can be tested perfectly well with inline event loops).
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from realtime.hub import EventHub, get_hub, reset_hub
from realtime.hub import EventType, StreamEvent


# ---------------------------------------------------------------------------
# Helper: run an async test body in a fresh event loop (sync-compatible).
# ---------------------------------------------------------------------------

def _run(coro):
    """Execute an async test function in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 1. Ordering
# ---------------------------------------------------------------------------

class TestOrdering:
    """Events are delivered to a subscriber in publish order."""

    def test_events_arrive_in_publish_order(self):
        async def _test():
            hub = EventHub(buffer_size=100, client_queue_size=100)
            loop = asyncio.get_running_loop()
            hub.attach_loop(loop)

            client = hub.subscribe("tenant-a")
            assert client is not None

            for i in range(5):
                hub.publish("tenant-a", EventType.TASK_UPDATED, {"seq": i})

            received: list[StreamEvent] = []
            await asyncio.sleep(0.05)
            while not client.queue.empty():
                received.append(client.queue.get_nowait())

            assert len(received) == 5
            seqs = [e.payload["seq"] for e in received]
            assert seqs == [0, 1, 2, 3, 4]

        _run(_test())


# ---------------------------------------------------------------------------
# 2. Last-Event-ID resume
# ---------------------------------------------------------------------------

class TestLastEventIDResume:
    """A subscriber with a known last_event_id receives missed events."""

    def test_resume_delivers_missed_events(self):
        async def _test():
            hub = EventHub(buffer_size=100, client_queue_size=100)
            loop = asyncio.get_running_loop()
            hub.attach_loop(loop)

            for i in range(10):
                hub.publish("tenant-a", EventType.ALERT_CREATED, {"idx": i})

            client = hub.subscribe("tenant-a", last_event_id=7)
            assert client is not None

            received: list[StreamEvent] = []
            while not client.queue.empty():
                received.append(client.queue.get_nowait())

            assert len(received) == 3
            assert [e.payload["idx"] for e in received] == [7, 8, 9]

        _run(_test())

    def test_resume_beyond_buffer_emits_resync(self):
        async def _test():
            hub = EventHub(buffer_size=5, client_queue_size=100)
            loop = asyncio.get_running_loop()
            hub.attach_loop(loop)

            for i in range(10):
                hub.publish("tenant-a", EventType.TASK_UPDATED, {"seq": i})

            client = hub.subscribe("tenant-a", last_event_id=2)
            assert client is not None
            assert client.resync_pending is True

        _run(_test())


# ---------------------------------------------------------------------------
# 3. Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """Events for tenant-A never reach tenant-B's subscriber."""

    def test_cross_tenant_events_not_delivered(self):
        async def _test():
            hub = EventHub(buffer_size=100, client_queue_size=100)
            loop = asyncio.get_running_loop()
            hub.attach_loop(loop)

            client_a = hub.subscribe("tenant-a")
            client_b = hub.subscribe("tenant-b")
            assert client_a is not None and client_b is not None

            hub.publish("tenant-a", EventType.HEALTH_CHANGED, {"score": 90})
            await asyncio.sleep(0.05)

            assert not client_a.queue.empty()
            assert client_b.queue.empty()

            evt = client_a.queue.get_nowait()
            assert evt.payload["score"] == 90

        _run(_test())


# ---------------------------------------------------------------------------
# 4. Redaction — events carry only ids and status, never parameters/secrets
# ---------------------------------------------------------------------------

class TestRedaction:
    """Approval events NEVER contain raw parameters, tokens, or secrets."""

    def test_approval_event_payload_has_no_parameters(self):
        async def _test():
            hub = EventHub(buffer_size=100, client_queue_size=100)
            loop = asyncio.get_running_loop()
            hub.attach_loop(loop)

            client = hub.subscribe("tenant-a")
            assert client is not None

            hub.publish("tenant-a", EventType.APPROVAL_CREATED, {
                "id": "approval-123",
                "task_id": "task-456",
                "tool": "desktop_open_app",
                "status": "pending_approval",
            })
            await asyncio.sleep(0.05)

            evt = client.queue.get_nowait()
            payload_str = str(evt.payload)
            assert "parameters" not in evt.payload
            assert "token" not in evt.payload
            assert "secret" not in evt.payload
            assert "grant" not in payload_str.lower()

        _run(_test())


# ---------------------------------------------------------------------------
# 5. Backpressure — slow client gets drop-oldest + resync
# ---------------------------------------------------------------------------

class TestBackpressure:
    """When a client's queue is full, the oldest event is dropped and
    a resync flag is set."""

    def test_drop_oldest_on_overflow(self):
        async def _test():
            hub = EventHub(buffer_size=100, client_queue_size=3)
            loop = asyncio.get_running_loop()
            hub.attach_loop(loop)

            client = hub.subscribe("tenant-a")
            assert client is not None

            for i in range(5):
                hub.publish("tenant-a", EventType.TASK_UPDATED, {"seq": i})
                await asyncio.sleep(0.01)

            assert client.queue.qsize() <= 3
            assert client.resync_pending is True

            received = []
            while not client.queue.empty():
                received.append(client.queue.get_nowait())
            seqs = [e.payload["seq"] for e in received]
            assert 4 in seqs  # Most recent always present.

        _run(_test())


# ---------------------------------------------------------------------------
# 6. Connection cap
# ---------------------------------------------------------------------------

class TestConnectionCap:
    """Beyond max_connections, subscribe returns None (route returns 503)."""

    def test_cap_rejects_excess_clients(self):
        async def _test():
            hub = EventHub(buffer_size=10, client_queue_size=10, max_connections=2)
            loop = asyncio.get_running_loop()
            hub.attach_loop(loop)

            c1 = hub.subscribe("tenant-a")
            c2 = hub.subscribe("tenant-a")
            c3 = hub.subscribe("tenant-a")

            assert c1 is not None
            assert c2 is not None
            assert c3 is None
            assert hub.client_count == 2

        _run(_test())


# ---------------------------------------------------------------------------
# 7. Hub failure isolation — approval gate never depends on the hub
# ---------------------------------------------------------------------------

class TestHubFailureIsolation:
    """If the hub is broken, publish() swallows errors and never raises
    to the caller."""

    def test_publish_failure_does_not_propagate(self):
        hub = EventHub(buffer_size=10, client_queue_size=10)
        # Force an internal AttributeError by destroying the lock.
        hub._lock = None
        result = hub.publish("tenant-a", EventType.TASK_UPDATED, {"id": "x"})
        assert result is None

    def test_approval_unaffected_by_broken_hub(self):
        """Full integration: create an approval while the hub is broken;
        assert the approval row is still committed and returned."""
        reset_hub()
        hub = get_hub()
        # Sabotage: make emit() raise on every call.
        with patch("realtime.publishers.get_hub", side_effect=RuntimeError("hub down")):
            from fastapi.testclient import TestClient
            from main import app

            with TestClient(app) as client:
                res = client.post("/api/desktop/execute", json={
                    "tool": "desktop_open_app",
                    "parameters": {"app_name": "TextEdit"},
                })
                # The desktop/execute route creates a PENDING approval.
                assert res.status_code == 202
                body = res.json()
                assert body["status"] == "pending_approval"
                approval_id = body["approval_id"]
                get_res = client.get(f"/api/approvals/{approval_id}")
                assert get_res.status_code == 200

        reset_hub()
