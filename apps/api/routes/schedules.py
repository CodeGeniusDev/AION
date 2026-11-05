"""Schedule endpoints — recurring desktop actions, approval-gated by design.

A schedule is a *promise to ask*, not a promise to do: when it fires the
runner creates a pending approval through the same create-only service
path chat uses. Nothing here executes anything, touches the bridge, or
can bypass the human decision — approving a schedule-produced approval
is the identical /api/approvals/{id}/approve flow.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from auth.dependency import get_current_principal, require_role, resolve_tenant_id
from models.auth import Role
from memory.schedule_store import (
    SQLiteScheduleStore,
    get_default_schedule_store,
    new_schedule,
)
from models.schedules import Schedule, ScheduleCreateRequest, SchedulesResponse
from services.approval_service import known_desktop_tools

router = APIRouter(tags=["schedules"])

WRITE_ROLES: set[Role] = {"admin", "user"}


def _to_public(record) -> Schedule:
    return Schedule(**record.model_dump())


@router.get("/schedules", response_model=SchedulesResponse)
async def list_schedules(
    principal=Depends(get_current_principal),
) -> SchedulesResponse:
    store: SQLiteScheduleStore = get_default_schedule_store()
    tenant_id = resolve_tenant_id(principal)
    return SchedulesResponse(items=[_to_public(r) for r in store.list_all(tenant_id)])


@router.get("/schedules/{schedule_id}", response_model=Schedule)
async def get_schedule(
    schedule_id: str,
    principal=Depends(get_current_principal),
) -> Schedule:
    record = get_default_schedule_store().get(schedule_id)
    # Another tenant's schedule does not exist here (same 404 discipline
    # as the approvals ledger).
    if record is None or record.tenant_id != resolve_tenant_id(principal):
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _to_public(record)


@router.post("/schedules", response_model=Schedule, status_code=201)
async def create_schedule(
    payload: ScheduleCreateRequest,
    principal=Depends(get_current_principal),
) -> Schedule:
    """Create a recurring (or one-shot) pending-approval generator.
    The tool must be a real desktop tool; protected tools stay protected
    — the schedule only ever reaches the queue, never the bridge."""
    require_role(principal, allowed=WRITE_ROLES)
    if payload.tool not in known_desktop_tools():
        raise HTTPException(status_code=404, detail=f"Unknown desktop tool: {payload.tool}")
    store = get_default_schedule_store()
    record = new_schedule(
        name=payload.name,
        tool=payload.tool,
        parameters=payload.parameters,
        interval_seconds=payload.interval_seconds,
        delay_seconds=payload.delay_seconds,
        tenant_id=resolve_tenant_id(principal),
    )
    return _to_public(store.create(record))


@router.post("/schedules/{schedule_id}/pause", response_model=Schedule)
async def pause_schedule(
    schedule_id: str,
    principal=Depends(get_current_principal),
) -> Schedule:
    require_role(principal, allowed=WRITE_ROLES)
    store = get_default_schedule_store()
    record = store.get(schedule_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if record.status not in ("active", "paused"):
        raise HTTPException(status_code=409, detail=f"Schedule is {record.status}")
    return _to_public(store.set_status(schedule_id, "paused"))


@router.post("/schedules/{schedule_id}/resume", response_model=Schedule)
async def resume_schedule(
    schedule_id: str,
    principal=Depends(get_current_principal),
) -> Schedule:
    require_role(principal, allowed=WRITE_ROLES)
    store = get_default_schedule_store()
    record = store.get(schedule_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if record.status != "paused":
        raise HTTPException(status_code=409, detail=f"Schedule is {record.status}, only paused schedules resume")
    # First fire one interval from now — never a burst for paused time.
    gap = record.interval_seconds if record.interval_seconds > 0 else 60
    next_run = (datetime.now(timezone.utc) + timedelta(seconds=gap)).isoformat()
    return _to_public(store.rearm(schedule_id, next_run_at=next_run))


@router.delete("/schedules/{schedule_id}", response_model=Schedule)
async def cancel_schedule(
    schedule_id: str,
    principal=Depends(get_current_principal),
) -> Schedule:
    """Cancel is terminal but non-destructive: the row stays for audit
    history with status `canceled`."""
    require_role(principal, allowed=WRITE_ROLES)
    store = get_default_schedule_store()
    record = store.get(schedule_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if record.status in ("completed", "canceled"):
        return _to_public(record)
    return _to_public(store.set_status(schedule_id, "canceled"))
