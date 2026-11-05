"""Real-time SSE hub: tenant-aware subscriber registry, bounded ring buffer
for Last-Event-ID resume, per-client asyncio queues with drop-oldest
backpressure, connection cap, and a publish helper that swallows its own
errors.

Design contract:
- publish() is SAFE to call from any thread (sync stores or async routes).
- A hub exception NEVER propagates to the caller — publish() swallows all
  internal errors after logging, so the approval gate and task stores are
  never blocked or altered by hub failure.
- Ring buffer (default 512 events) supports Last-Event-ID resume; once an
  event ages out the client receives a resync frame.
- Per-client asyncio.Queue with bounded size (default 64); overflow drops
  the oldest event and enqueues a synthetic RESYNC to signal the client
  should re-fetch from REST.
- Connection cap (default 50) prevents resource exhaustion.
- Events carry ONLY ids and changed status strings — NEVER secrets, tokens,
  or unredacted approval parameters.

No external dependencies beyond stdlib + asyncio.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

logger = logging.getLogger("aion.realtime")


# ---------------------------------------------------------------------------
# Event schema
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    """Business events observable via GET /api/stream."""

    TASK_UPDATED = "task.updated"
    APPROVAL_CREATED = "approval.created"
    APPROVAL_UPDATED = "approval.updated"
    ALERT_CREATED = "alert.created"
    ALERT_UPDATED = "alert.updated"
    AGENT_STATUS = "agent.status"
    HEALTH_CHANGED = "health.changed"
    BRIDGE_STATUS = "bridge.status"
    WORKFLOW_RUN_UPDATED = "workflow.run.updated"
    SCHEDULE_FIRED = "schedule.fired"
    MEMORY_WRITTEN = "memory.written"
    CONVERSATION_UPDATED = "conversation.updated"
    # Internal: signals a client missed events due to backpressure.
    RESYNC = "resync"


@dataclass(slots=True)
class StreamEvent:
    """A single event delivered over SSE.

    Attributes:
        id: Monotonically-increasing integer assigned by the hub.
        tenant_id: Scoping key — subscribers only receive events for their tenant.
        type: The business event type.
        payload: Minimal dict (ids + changed fields). Never secrets.
    """

    id: int
    tenant_id: str
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)

    def sse_frame(self) -> str:
        """Format as a Server-Sent Events frame."""
        data = {"type": self.type.value, **self.payload}
        return f"id: {self.id}\nevent: {self.type.value}\ndata: {json.dumps(data, separators=(',', ':'), default=str)}\n\n"


# ---------------------------------------------------------------------------
# Hub internals
# ---------------------------------------------------------------------------

DEFAULT_BUFFER_SIZE = 512
DEFAULT_CLIENT_QUEUE_SIZE = 64
DEFAULT_MAX_CONNECTIONS = 50


class _ClientSub:
    """Internal per-connection subscriber state."""

    __slots__ = ("tenant_id", "queue", "loop", "resync_pending")

    def __init__(self, tenant_id: str, loop: asyncio.AbstractEventLoop, queue_size: int):
        self.tenant_id = tenant_id
        self.loop = loop
        self.queue: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=queue_size)
        self.resync_pending = False


# ---------------------------------------------------------------------------
# EventHub
# ---------------------------------------------------------------------------


class EventHub:
    """Process-wide singleton (accessed via get_hub())."""

    def __init__(
        self,
        *,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        client_queue_size: int = DEFAULT_CLIENT_QUEUE_SIZE,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
    ):
        self._buffer: deque[StreamEvent] = deque(maxlen=buffer_size)
        self._next_id: int = 1
        self._clients: set[_ClientSub] = set()
        self._lock = threading.Lock()
        self._client_queue_size = client_queue_size
        self._max_connections = max_connections
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Loop registration (called from FastAPI lifespan startup)
    # ------------------------------------------------------------------

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store a reference to the running event loop so publish() can
        dispatch from worker threads via call_soon_threadsafe."""
        self._loop = loop

    # ------------------------------------------------------------------
    # Publish (thread-safe, never raises)
    # ------------------------------------------------------------------

    def publish(self, tenant_id: str, event_type: EventType, payload: dict) -> int | None:
        """Record and fan-out a business event. Returns the event id, or
        None if the hub is in a broken state (loop gone, etc.). The caller
        MUST treat the return value as advisory — publish never raises."""
        try:
            with self._lock:
                event_id = self._next_id
                self._next_id += 1
                evt = StreamEvent(
                    id=event_id, tenant_id=tenant_id, type=event_type, payload=payload,
                )
                self._buffer.append(evt)
                targets = [c for c in self._clients if c.tenant_id == tenant_id]

            # Dispatch outside the lock to avoid holding it during
            # call_soon_threadsafe (which may invoke on a different thread).
            loop = self._loop
            if loop is None or loop.is_closed():
                return event_id

            for client in targets:
                try:
                    loop.call_soon_threadsafe(self._offer, client, evt)
                except RuntimeError:
                    pass

            return event_id
        except Exception:
            # Hub failure must NEVER propagate to the approval gate,
            # task store, or any caller.
            logger.exception("realtime hub publish swallowed an internal error")
            return None

    def _offer(self, client: _ClientSub, evt: StreamEvent) -> None:
        """Enqueue to one client's asyncio.Queue. Called on the event loop.
        On overflow, drop the oldest item and mark resync."""
        if client.queue.full():
            try:
                client.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            client.resync_pending = True
        try:
            client.queue.put_nowait(evt)
        except asyncio.QueueFull:
            pass

    # ------------------------------------------------------------------
    # Subscribe / unsubscribe
    # ------------------------------------------------------------------

    def subscribe(self, tenant_id: str, last_event_id: int | None = None) -> _ClientSub | None:
        """Register a new client. Returns None if the connection cap is hit.
        If last_event_id is given, queued events are pre-filled from the
        ring buffer (catch-up replay).

        Must be called from within an async context (the SSE route handler).
        Lazily captures the running loop so attach_loop is not mandatory.
        """
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        if self._loop is None or self._loop.is_closed():
            self._loop = running_loop

        with self._lock:
            if len(self._clients) >= self._max_connections:
                return None
            loop = self._loop
            if loop is None or loop.is_closed():
                return None
            client = _ClientSub(tenant_id, loop, self._client_queue_size)

            # Replay from ring buffer for Last-Event-ID resume.
            if last_event_id is not None:
                missed = [
                    e for e in self._buffer
                    if e.id > last_event_id and e.tenant_id == tenant_id
                ]
                oldest_in_buffer = self._buffer[0].id if self._buffer else 0
                if last_event_id < oldest_in_buffer and self._buffer:
                    client.resync_pending = True
                for e in missed:
                    try:
                        client.queue.put_nowait(e)
                    except asyncio.QueueFull:
                        client.resync_pending = True
                        break

            self._clients.add(client)
            return client

    def unsubscribe(self, client: _ClientSub) -> None:
        with self._lock:
            self._clients.discard(client)

    # ------------------------------------------------------------------
    # Async iteration (called from the SSE route generator)
    # ------------------------------------------------------------------

    async def stream(self, client: _ClientSub) -> AsyncIterator[StreamEvent]:
        """Yield events for this client. Emits a RESYNC frame before the
        next real event if backpressure dropped items. Terminates cleanly
        when the generator is cancelled (client disconnect)."""
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(client.queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Heartbeat comment — keeps proxies from closing the conn.
                    yield StreamEvent(
                        id=0, tenant_id=client.tenant_id, type=EventType.RESYNC,
                        payload={"heartbeat": True},
                    )
                    continue

                if client.resync_pending:
                    client.resync_pending = False
                    yield StreamEvent(
                        id=evt.id - 1 if evt.id > 1 else 0,
                        tenant_id=client.tenant_id,
                        type=EventType.RESYNC,
                        payload={"reason": "backpressure"},
                    )

                yield evt
        except asyncio.CancelledError:
            return

    # ------------------------------------------------------------------
    # Introspection (for tests)
    # ------------------------------------------------------------------

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    @property
    def buffer_size(self) -> int:
        with self._lock:
            return len(self._buffer)

    @property
    def next_id(self) -> int:
        with self._lock:
            return self._next_id


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_hub: EventHub | None = None


def get_hub() -> EventHub:
    global _hub
    if _hub is None:
        _hub = EventHub()
    return _hub


def reset_hub() -> None:
    """Test helper — discard the singleton so the next get creates fresh."""
    global _hub
    _hub = None
