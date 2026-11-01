"""Desktop tool execution endpoints (approval-gated).

POST /api/desktop/execute does NOT execute anything. It creates a task
plus a pending_approval ledger row and an alert, and returns 202. The
action only reaches the desktop bridge after a human approves it through
/api/approvals/{id}/approve — there is no auto-approval path and this
route never touches the bridge secret.
"""

from fastapi import APIRouter, Depends, HTTPException

from auth.dependency import get_current_principal, resolve_tenant_id, require_role
from models.approval import ApprovalExecuteResponse, ApprovalExecutionRequest
from models.auth import Role
from services.approval_service import ApprovalError, get_approval_service

router = APIRouter(tags=["desktop"])

WRITE_ROLES: set[Role] = {"admin", "user"}


@router.post("/desktop/execute", response_model=ApprovalExecuteResponse, status_code=202)
async def request_desktop_execution(
    payload: ApprovalExecutionRequest,
    principal=Depends(get_current_principal),
) -> ApprovalExecuteResponse:
    """Request a desktop tool execution. Always returns 202
    'pending_approval' (or 404 for an unknown tool / invalid task id,
    401/403 per the existing auth model). Never executes."""
    require_role(principal, allowed=WRITE_ROLES)
    service = get_approval_service()
    try:
        record = service.request_execution(
            tool=payload.tool,
            parameters=payload.parameters,
            tenant_id=resolve_tenant_id(principal),
            actor_key_id=principal.key_id if principal is not None else None,
            title=payload.title,
            task_id=payload.task_id,
        )
    except ApprovalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    # Dispatch is intentionally absent here: the request stage must never
    # call the bridge, whatever the tool or its parameters claim.
    return ApprovalExecuteResponse(
        approval_id=record.id,
        task_id=record.task_id,
        status="pending_approval",
        expires_at=record.expires_at,
        requires="human_approval",
    )
