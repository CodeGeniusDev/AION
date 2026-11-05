"""Thin publish wrappers for each event type.

Design contract:
- Callers NEVER build payload dicts inline — they pass typed keyword
  arguments, and this module constructs the minimal (ids + status) payload.
- Every wrapper is fire-and-forget: wraps hub.publish in try/except so a
  broken hub NEVER blocks or alters the approval gate, task store, or any
  other business path.
- Payloads contain ONLY ids and status strings. They NEVER carry raw
  parameters dicts, tokens, secrets, bridge URLs, or full message bodies.
"""

from __future__ import annotations

import logging
from typing import Any

from realtime.hub import EventType, get_hub

logger = logging.getLogger("aion.realtime.publishers")


def _publish(tenant_id: str, event_type: EventType, payload: dict[str, Any]) -> None:
    """Internal: best-effort publish. NEVER raises."""
    try:
        hub = get_hub()
        hub.publish(tenant_id, event_type, payload)
    except Exception:
        logger.warning("realtime publish swallowed error for %s", event_type.value)


# ---------------------------------------------------------------------------
# Approval events
# ---------------------------------------------------------------------------

def publish_approval_created(
    tenant_id: str, *, approval_id: str, task_id: str, tool: str,
) -> None:
    _publish(tenant_id, EventType.APPROVAL_CREATED, {
        "id": approval_id, "task_id": task_id, "tool": tool,
        "status": "pending_approval",
    })


def publish_approval_updated(
    tenant_id: str, *, approval_id: str, task_id: str, status: str,
) -> None:
    _publish(tenant_id, EventType.APPROVAL_UPDATED, {
        "id": approval_id, "task_id": task_id, "status": status,
    })


# ---------------------------------------------------------------------------
# Task events
# ---------------------------------------------------------------------------

def publish_task_updated(
    tenant_id: str, *, task_id: str, status: str,
) -> None:
    _publish(tenant_id, EventType.TASK_UPDATED, {
        "id": task_id, "status": status,
    })


# ---------------------------------------------------------------------------
# Alert events
# ---------------------------------------------------------------------------

def publish_alert_created(
    tenant_id: str, *, alert_id: str, category: str, tone: str,
) -> None:
    _publish(tenant_id, EventType.ALERT_CREATED, {
        "id": alert_id, "category": category, "tone": tone,
    })


def publish_alert_updated(
    tenant_id: str, *, alert_id: str, status: str,
) -> None:
    _publish(tenant_id, EventType.ALERT_UPDATED, {
        "id": alert_id, "status": status,
    })


# ---------------------------------------------------------------------------
# Conversation events
# ---------------------------------------------------------------------------

def publish_conversation_updated(
    tenant_id: str, *, conversation_id: str,
) -> None:
    _publish(tenant_id, EventType.CONVERSATION_UPDATED, {
        "conversation_id": conversation_id,
    })


# ---------------------------------------------------------------------------
# Schedule events
# ---------------------------------------------------------------------------

def publish_schedule_fired(
    tenant_id: str, *, schedule_id: str, approval_id: str,
) -> None:
    _publish(tenant_id, EventType.SCHEDULE_FIRED, {
        "schedule_id": schedule_id, "approval_id": approval_id,
    })


# ---------------------------------------------------------------------------
# Workflow events
# ---------------------------------------------------------------------------

def publish_workflow_run_updated(
    tenant_id: str, *, workflow_id: str, status: str,
) -> None:
    _publish(tenant_id, EventType.WORKFLOW_RUN_UPDATED, {
        "id": workflow_id, "status": status,
    })


# ---------------------------------------------------------------------------
# Memory events
# ---------------------------------------------------------------------------

def publish_memory_written(
    tenant_id: str, *, task_id: str, record_count: int,
) -> None:
    _publish(tenant_id, EventType.MEMORY_WRITTEN, {
        "task_id": task_id, "record_count": record_count,
    })


# ---------------------------------------------------------------------------
# Bridge / health events
# ---------------------------------------------------------------------------

def publish_bridge_status(
    tenant_id: str, *, reachable: bool, bridge_status: str | None = None,
) -> None:
    _publish(tenant_id, EventType.BRIDGE_STATUS, {
        "reachable": reachable, "status": bridge_status or "unknown",
    })


def publish_health_changed(
    tenant_id: str, *, score: int | None = None,
) -> None:
    _publish(tenant_id, EventType.HEALTH_CHANGED, {
        "score": score,
    })


# ---------------------------------------------------------------------------
# Agent events
# ---------------------------------------------------------------------------

def publish_agent_status(
    tenant_id: str, *, agent_id: str, status: str,
) -> None:
    _publish(tenant_id, EventType.AGENT_STATUS, {
        "agent_id": agent_id, "status": status,
    })
