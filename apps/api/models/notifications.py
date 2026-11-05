"""Notification / alert data model.

Persistent notifications that survive page refresh and server restarts.
Notifications are auto-generated from system events (task completions,
task failures, agent activity) and can also be marked read/archived.
"""

from typing import Literal

from pydantic import BaseModel, Field

AlertCategory = Literal["task", "agent", "system", "memory", "approval"]
AlertTone = Literal["info", "success", "warning", "error"]


class AlertItem(BaseModel):
    id: str
    title: str
    description: str
    time: str
    category: AlertCategory
    unread: bool = True
    tone: AlertTone = "info"
    # Additive (Phase 1 header): ISO creation timestamp and optional
    # in-app deep link. Older clients ignore both; absent stays neutral.
    created_at: str = ""
    link: str | None = None


class AlertsResponse(BaseModel):
    items: list[AlertItem]
    total: int
    unread_count: int


class MarkReadRequest(BaseModel):
    alert_ids: list[str] = Field(default_factory=list)
