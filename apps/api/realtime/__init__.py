"""Real-time SSE layer — business-event notification hub for /api/stream.

Public API:
    get_hub()           → EventHub singleton
    reset_hub()         → test helper
    EventType           → enum of business event types
    StreamEvent         → dataclass for a single SSE event
    publish_*()         → thin wrappers per event type (from publishers)
"""

from realtime.hub import EventHub, EventType, StreamEvent, get_hub, reset_hub

__all__ = [
    "EventHub",
    "EventType",
    "StreamEvent",
    "get_hub",
    "reset_hub",
]
