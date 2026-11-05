"""Approval queue endpoints: list, inspect, approve, reject, audit.

Approve is the only path that can reach the desktop bridge: it wins the
atomic pending_approval -> running claim, registers a one-time grant on
the bridge, and dispatches the approved parameter snapshot (in a
BackgroundTask by default, or inline when AION_APPROVAL_DISPATCH_ASYNC=0).
A second approve of the same row can never dispatch a second execution —
the atomic claim turns it into HTTP 409.

The approve/reject endpoints are tenant-scoped and role-gated
(admin/user only; readonly gets 403). Responses expose only sanitized
parameters — never values for secret-like keys or file content, and
never any bridge secret or grant token.
"""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from auth.dependency import get_current_principal, resolve_tenant_id, require_role
from config import settings
from models.approval import ApprovalExecuteResponse, ApprovalRecord, ApprovalsResponse, AuditResponse
from models.auth import Role
from services.approval_service import ApprovalError, get_approval_service

router = APIRouter(tags=["approvals"])

WRITE_ROLES: set[Role] = {"admin", "user"}


def _http(exc: ApprovalError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/approvals", response_model=ApprovalsResponse)
async def list_approvals(
    status: str | None = None,
    limit: int = 100,
    principal=Depends(get_current_principal),
) -> ApprovalsResponse:
    """List approvals for the caller's tenant, newest first. Any
    authenticated role may read (approval decisions still require
    approve/reject, which are write-role-gated)."""
    service = get_approval_service()
    items = service.list_approvals(
        tenant_id=resolve_tenant_id(principal), status=status, limit=min(limit, 500),
    )
    return ApprovalsResponse(items=items, total=len(items))


@router.get("/approvals/{approval_id}", response_model=ApprovalRecord)
async def get_approval(
    approval_id: str,
    principal=Depends(get_current_principal),
) -> ApprovalRecord:
    service = get_approval_service()
    try:
        return service.get_approval(approval_id, tenant_id=resolve_tenant_id(principal))
    except ApprovalError as exc:
        raise _http(exc) from exc


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalExecuteResponse, status_code=202)
async def approve_action(
    approval_id: str,
    background_tasks: BackgroundTasks,
    principal=Depends(get_current_principal),
) -> ApprovalExecuteResponse:
    """Explicit human approval: claims the row exactly once and schedules
    the bridge dispatch under a one-time grant. 409 = already claimed or
    terminal (including a double approve); 410 = expired."""
    require_role(principal, allowed=WRITE_ROLES)
    service = get_approval_service()
    tenant_id = resolve_tenant_id(principal)
    actor_key_id = principal.key_id if principal is not None else None
    try:
        claimed = service.approve_and_claim(
            approval_id, tenant_id=tenant_id, actor_key_id=actor_key_id,
        )
    except ApprovalError as exc:
        raise _http(exc) from exc

    def _dispatch() -> None:
        # Runs after the response is sent (or inline, see below). All
        # terminal-state bookkeeping happens inside service.dispatch, so a
        # raising dispatch here can never leave the row claimable again.
        try:
            service.dispatch(claimed, tenant_id=tenant_id)
        except ApprovalError:
            pass  # already finalized + audited + task-synced inside dispatch

    if settings.approval_dispatch_async:
        background_tasks.add_task(_dispatch)
    else:
        _dispatch()

    return ApprovalExecuteResponse(
        approval_id=claimed.id,
        task_id=claimed.task_id,
        status="running",
        expires_at=claimed.expires_at,
        requires="human_approval",
    )


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRecord)
async def reject_action(
    approval_id: str,
    principal=Depends(get_current_principal),
) -> ApprovalRecord:
    """Reject a pending action. Terminal: the tool never executes and a
    later approve attempt returns 409."""
    require_role(principal, allowed=WRITE_ROLES)
    service = get_approval_service()
    try:
        record = service.reject(
            approval_id,
            tenant_id=resolve_tenant_id(principal),
            actor_key_id=principal.key_id if principal is not None else None,
        )
    except ApprovalError as exc:
        raise _http(exc) from exc
    return ApprovalRecord.model_validate(record)


@router.get("/audit", response_model=AuditResponse)
async def list_audit(
    approval_id: str | None = None,
    limit: int = 100,
    principal=Depends(get_current_principal),
) -> AuditResponse:
    """Read-only, append-only execution audit trail for the caller's
    tenant. There is no API that mutates or deletes these rows."""
    service = get_approval_service()
    try:
        items: list[dict[str, Any]] = service.get_audit(
            tenant_id=resolve_tenant_id(principal), approval_id=approval_id,
            limit=min(limit, 500),
        )
    except ApprovalError as exc:
        raise _http(exc) from exc
    return AuditResponse(items=items, total=len(items))
