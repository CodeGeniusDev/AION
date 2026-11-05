"""Desktop tool approval schemas.

`ApprovalRecord` is the API-facing view of one human-in-the-loop desktop
tool execution request. Note the two deliberate omissions:

* ``parameters`` is always the *sanitized* snapshot — raw values for
  secret-like keys and file content are never serialized into responses.
* There is no field for the one-time execution grant token or its hash.
  The raw token exists only in-flight between the backend and the bridge;
  the ledger stores only its SHA-256 hash, and even that is not exposed.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# The ledger's own lifecycle. `approved` is transient: approve+claim happen
# in one step, so observers normally see pending_approval -> running.
ApprovalStatus = Literal[
    "pending_approval", "approved", "running", "completed",
    "failed", "rejected", "expired",
]


class ApprovalRecord(BaseModel):
    id: str
    task_id: str
    # Internal tenant scoping only — excluded from every serialized
    # response so the API contract stays what the plan specifies.
    tenant_id: str = Field(default="default", exclude=True)
    tool: str
    parameters: dict[str, Any] = Field(default_factory=dict)  # sanitized
    status: ApprovalStatus
    created_at: str
    expires_at: str
    approved_at: str | None = None
    approved_by_key_id: str | None = None
    claimed_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


class ApprovalExecutionRequest(BaseModel):
    """POST /api/desktop/execute body: creates a pending approval only —
    nothing executes until a human approves through /api/approvals."""

    tool: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None
    task_id: str | None = None  # link to an existing task instead of creating one


class ApprovalExecuteResponse(BaseModel):
    """202 response for both the execute request and the approve endpoint."""

    approval_id: str
    task_id: str
    status: ApprovalStatus
    expires_at: str
    requires: str = "human_approval"


class ApprovalsResponse(BaseModel):
    items: list[ApprovalRecord]
    total: int


class DesktopHealthResponse(BaseModel):
    """Bridge connectivity for the Desktop tab. Carries only the bridge's
    public health status — never the URL, secret, tokens or tool data."""

    reachable: bool
    status: str | None = None


class AuditEvent(BaseModel):
    """One append-only audit-log entry. `detail` is sanitized and must
    never contain parameter values, the bridge secret, or grant tokens."""

    seq: int
    ts: str
    event: str
    approval_id: str
    task_id: str | None = None
    actor_key_id: str | None = None
    detail: str | None = None


class AuditResponse(BaseModel):
    items: list[AuditEvent]
    total: int
