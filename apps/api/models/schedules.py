"""Scheduled desktop action schemas.

A ``Schedule`` describes a desktop tool invocation that should be
attempted on an interval. The critical invariant: **firing a schedule
only creates a pending approval** — exactly what a human request does.
A schedule can never execute, approve, or observe grant tokens; every
fire still requires an explicit human decision in the approval queue.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ScheduleStatus = Literal["active", "paused", "completed", "canceled"]


class Schedule(BaseModel):
    id: str
    name: str
    tool: str
    tenant_id: str = "default"  # approvals produced at fire time land here
    parameters: dict[str, Any] = Field(default_factory=dict)
    interval_seconds: float = 0  # 0 = one-shot
    status: ScheduleStatus = "active"
    next_run_at: str | None  # ISO-8601 UTC; None once finalized
    last_run_at: str | None = None
    last_approval_id: str | None = None
    last_error: str | None = None
    fire_count: int = 0
    created_at: str
    updated_at: str


class SchedulesResponse(BaseModel):
    items: list[Schedule]


class ScheduleCreateRequest(BaseModel):
    """POST /api/schedules body. Creates a schedule only — nothing runs
    until the clock reaches next_run_at AND a human approves the
    pending approval the fire produces."""

    name: str = Field(min_length=1, max_length=200)
    tool: str = Field(min_length=1, max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)
    interval_seconds: float = Field(default=0, ge=0, le=7 * 24 * 3600)
    delay_seconds: float = Field(default=0, ge=0, le=30 * 24 * 3600)

    @field_validator("parameters")
    @classmethod
    def parameters_must_be_json_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        # Round-trip through JSON: rejects callables, sockets, NaN etc.
        # before they can reach the SQLite store. Values are still
        # sanitized again by the approval ledger at fire time.
        import json

        try:
            json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("parameters must be JSON-serializable") from exc
        return value
