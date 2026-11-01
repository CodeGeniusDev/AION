"""Approval service: the orchestration between the approval ledger, the
task store, the alert pipeline and the desktop bridge client.

Rules this service enforces (and the routes above it rely on):

* A protected desktop tool NEVER executes without a human having
  explicitly approved a ledger row. There is no auto-approval path.
* Approve + claim is one atomic transition; whoever wins it dispatches.
  Everyone else gets a conflict — the action runs at most once.
* Execution uses the stored approved parameter snapshot (verified by
  SHA-256 before dispatch), never a re-submitted payload.
* Anything that can go wrong on the way to the bridge (unreachable,
  rejected, non-JSON) finalizes the approval `failed` with an audit
  event. Partial-execution state is never claimed.
* The bridge secret and grant tokens never reach the ledger's audit
  details, alerts, or API responses.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from config import settings
from memory.approval_store import ApprovalStore, canonical_hash, get_default_approval_store
from models.approval import ApprovalRecord
from services.desktop_bridge_client import BridgeError, DesktopBridgeClient, new_grant_token
from services.task_service import _default_service as task_service


class ApprovalError(Exception):
    """Domain error with the HTTP status the route should surface."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class ApprovalOutcome:
    record: ApprovalRecord  # post-claim row (status running), raw params
    execution: dict[str, Any]  # bridge response for the granted execution


def _protected_set() -> set[str]:
    # Parsed per call (not at import) so tests can monkeypatch
    # settings.protected_desktop_tools and change the policy live.
    return {t.strip() for t in settings.protected_desktop_tools.split(",") if t.strip()}


def known_desktop_tools() -> set[str]:
    return _protected_set() | {
        "desktop_list_apps", "voice_listen", "voice_say",
    }


def is_protected(tool: str) -> bool:
    return tool in _protected_set()


class ApprovalService:
    def __init__(
        self,
        store: ApprovalStore | None = None,
        bridge_client: DesktopBridgeClient | None = None,
    ) -> None:
        self.store = store or get_default_approval_store()
        # Resolved lazily-by-argument at dispatch time: tests inject a mock
        # client per call; production uses the real settings-derived client.
        self._bridge_client = bridge_client

    def bridge(self) -> DesktopBridgeClient:
        return self._bridge_client if self._bridge_client is not None else DesktopBridgeClient()

    # ------------------------------------------------------------------
    # Request (never executes)
    # ------------------------------------------------------------------

    def request_execution(
        self, *, tool: str, parameters: dict[str, Any],
        tenant_id: str, actor_key_id: str | None,
        title: str | None = None, task_id: str | None = None,
    ) -> ApprovalRecord:
        """Create a task (or link an existing one) plus a pending_approval
        ledger row, and push an alert. Nothing executes here — by design."""
        if tool not in known_desktop_tools():
            raise ApprovalError(404, f"Unknown desktop tool: {tool}")

        if task_id is not None:
            if task_service.get(task_id) is None:
                raise ApprovalError(404, f"Unknown task id: {task_id}")
        else:
            task = task_service.create(
                title or f"Desktop action: {tool}",
                agent="desktop", status="pending_approval",
            )
            task_id = task.id

        record = self.store.create(
            task_id=task_id, tenant_id=tenant_id,
            requested_by_key_id=actor_key_id, tool=tool,
            parameters=parameters, ttl_seconds=settings.approval_ttl_seconds,
        )
        self.store.audit(
            event="requested", approval_id=record.id, task_id=task_id,
            actor_key_id=actor_key_id, tenant_id=tenant_id,
            detail=f"tool={tool} params_hash={canonical_hash(parameters)[:12]} protected={is_protected(tool)}",
        )
        self._push_pending_alert(record)
        return record

    def _push_pending_alert(self, record: ApprovalRecord) -> None:
        """Reuse the existing alert pipeline so the current /alert UI shows
        pending approvals with zero frontend alert-code changes. The alert
        body carries no parameter values whatsoever."""
        try:
            from routes.chat import alert_store
            alert_store.create(
                title=f"Desktop action pending approval: {record.tool}",
                description=(
                    f"Approval {record.id} (task {record.task_id}) is waiting "
                    "for an explicit human decision in the Tasks approval queue."
                ),
                category="approval",
                tone="warning",
            )
        except Exception:
            # Alerts are best-effort notification; the ledger row is the
            # source of truth and must not depend on them.
            pass

    # ------------------------------------------------------------------
    # Reject (terminal, never executes)
    # ------------------------------------------------------------------

    def reject(
        self, approval_id: str, *, tenant_id: str, actor_key_id: str | None,
    ) -> ApprovalRecord:
        record = self._get_scoped(approval_id, tenant_id)
        self.store.sweep_expired(tenant_id=tenant_id)
        record = self._get_scoped(approval_id, tenant_id)
        rejected = self.store.reject(approval_id, tenant_id=tenant_id)
        if rejected is None:
            if record.status == "pending_approval" and self.store.is_expired(record):
                self._expire(record, actor_key_id, tenant_id, "expiry before approval")
            raise ApprovalError(409, f"Approval is not pending (status: {record.status}).")
        self.store.audit(
            event="rejected", approval_id=approval_id, task_id=rejected.task_id,
            actor_key_id=actor_key_id, tenant_id=tenant_id, detail=f"tool={rejected.tool}",
        )
        self._sync_task(rejected.task_id, "failed", reason="rejected by approver")
        return rejected

    # ------------------------------------------------------------------
    # Approve: atomic claim, then dispatch
    # ------------------------------------------------------------------

    def approve_and_claim(
        self, approval_id: str, *, tenant_id: str, actor_key_id: str | None,
    ) -> ApprovalRecord:
        """Win the pending_approval -> running transition or raise. Never
        touches the bridge — dispatch happens after this returns, so a
        losing concurrent approver (409) can never cause a second run."""
        self.store.sweep_expired(tenant_id=tenant_id)
        record = self._get_scoped(approval_id, tenant_id)
        claimed = self.store.approve_and_claim(
            approval_id, tenant_id=tenant_id, actor_key_id=actor_key_id,
        )
        if claimed is None:
            current = self._get_scoped(approval_id, tenant_id)
            if current.status == "expired" or (
                current.status == "pending_approval" and self.store.is_expired(current)
            ):
                self._expire(current, actor_key_id, tenant_id, "expiry before approval")
                raise ApprovalError(410, "Approval request expired before it was approved.")
            raise ApprovalError(
                409, f"Approval cannot be claimed (status: {current.status}). "
                     "Each approval can only be claimed once.",
            )
        # Integrity: what was claimed must still hash to the approved snapshot.
        snapshot = self.store.params_snapshot(approval_id)
        if snapshot is None or snapshot[1] != canonical_hash(claimed.parameters):
            self.store.finalize(approval_id, "failed", error="parameter snapshot mismatch")
            self.store.audit(
                event="failed", approval_id=approval_id, task_id=claimed.task_id,
                actor_key_id=actor_key_id, tenant_id=tenant_id,
                detail="params_hash mismatch between claim and snapshot",
            )
            raise ApprovalError(500, "Approved parameter snapshot failed integrity check.")
        self.store.audit(
            event="approved", approval_id=approval_id, task_id=claimed.task_id,
            actor_key_id=actor_key_id, tenant_id=tenant_id, detail=f"tool={claimed.tool}",
        )
        self.store.audit(
            event="claimed", approval_id=approval_id, task_id=claimed.task_id,
            actor_key_id=actor_key_id, tenant_id=tenant_id, detail="dispatch scheduled",
        )
        self._sync_task(claimed.task_id, "running")
        return claimed

    def dispatch(self, claimed: ApprovalRecord, *, tenant_id: str) -> ApprovalOutcome:
        """Register a one-time grant on the bridge and execute the approved
        snapshot under it. Safe-failure: any bridge error finalizes the row
        `failed` (with an audit event) and raises — nothing is retried, a
        fresh approval must be requested."""
        bridge = self.bridge()
        token = new_grant_token()
        self.store.set_token_hash(claimed.id, hashlib.sha256(token.encode()).hexdigest())
        try:
            bridge.register_grant(
                approval_id=claimed.id, tool=claimed.tool,
                token=token, expires_at=claimed.expires_at,
            )
            self.store.audit(
                event="granted", approval_id=claimed.id, task_id=claimed.task_id,
                tenant_id=tenant_id, detail=f"tool={claimed.tool} grant registered on bridge",
            )
            execution = bridge.execute(
                tool=claimed.tool, parameters=claimed.parameters,
                task_id=claimed.task_id, approval_id=claimed.id, token=token,
            )
        except BridgeError as exc:
            reason = str(exc)[:200]  # BridgeError messages never contain the secret or token
            self.store.finalize(claimed.id, "failed", error=reason)
            self.store.audit(
                event="failed", approval_id=claimed.id, task_id=claimed.task_id,
                tenant_id=tenant_id, detail=f"bridge failure: {reason}",
            )
            self._sync_task(claimed.task_id, "failed", reason=f"bridge failure: {reason}")
            raise ApprovalError(502, f"Desktop execution failed: {reason}") from exc

        success = bool(execution.get("success", False))
        if success:
            self.store.finalize(claimed.id, "completed")
            self.store.audit(
                event="executed", approval_id=claimed.id, task_id=claimed.task_id,
                tenant_id=tenant_id,
                detail=f"tool={claimed.tool} success=true duration_ms={execution.get('duration_ms')}",
            )
            self._sync_task(claimed.task_id, "completed")
        else:
            # The grant was consumed — the tool ran and reported failure.
            # The bridge reports errors both top-level and nested under
            # 'result', so check both before defaulting.
            result = execution.get("result") or {}
            error = (
                execution.get("error")
                or (result.get("error") if isinstance(result, dict) else None)
                or "tool reported failure"
            )
            error = str(error)[:200]
            self.store.finalize(claimed.id, "failed", error=error)
            self.store.audit(
                event="failed", approval_id=claimed.id, task_id=claimed.task_id,
                tenant_id=tenant_id, detail=f"tool={claimed.tool} success=false",
            )
            self._sync_task(claimed.task_id, "failed", reason=error)
        final = self.store.get(claimed.id)
        assert final is not None
        return ApprovalOutcome(record=final, execution=execution)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_approvals(
        self, *, tenant_id: str, status: str | None = None, limit: int = 100,
    ) -> list[ApprovalRecord]:
        self.store.sweep_expired(tenant_id=tenant_id)
        records = self.store.list(tenant_id=tenant_id, status=status, limit=limit)
        return [self.store.to_public(r) for r in records]

    def get_approval(self, approval_id: str, *, tenant_id: str) -> ApprovalRecord:
        record = self._get_scoped(approval_id, tenant_id)
        return self.store.to_public(record)

    def get_audit(
        self, *, tenant_id: str, approval_id: str | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        if approval_id:
            self._get_scoped(approval_id, tenant_id)  # 404 before leaking another tenant's trail
        return self.store.list_audit(tenant_id=tenant_id, approval_id=approval_id, limit=limit)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_scoped(self, approval_id: str, tenant_id: str) -> ApprovalRecord:
        record = self.store.get(approval_id)
        if record is None or record.tenant_id != tenant_id:
            # Same answer for "doesn't exist" and "belongs to someone else":
            # no enumeration oracle.
            raise ApprovalError(404, f"Approval not found: {approval_id}")
        return record

    def _expire(
        self, record: ApprovalRecord, actor_key_id: str | None,
        tenant_id: str, reason: str,
    ) -> None:
        self.store.mark_expired(record.id, reason=reason)
        self.store.audit(
            event="expired", approval_id=record.id, task_id=record.task_id,
            actor_key_id=actor_key_id, tenant_id=tenant_id, detail=f"tool={record.tool} {reason}",
        )
        self._sync_task(record.task_id, "failed", reason=reason)

    def _sync_task(self, task_id: str, status: str, *, reason: str | None = None) -> None:
        """Flow the linked task through the existing TaskStatus machine
        (pending_approval -> running -> completed/failed). Best-effort:
        the approval ledger, not the task row, is the security boundary."""
        try:
            if reason:
                from models.tool import ToolOutput
                task_service.update_output(task_id, ToolOutput(
                    tool_id="approval", task_id=task_id, success=status == "completed",
                    content=reason,
                ))
            task_service.update_status(task_id, status)
        except Exception:
            pass


# Singleton for route convenience (tests construct their own instances).
_default_approval_service = ApprovalService()


def get_approval_service() -> ApprovalService:
    return _default_approval_service
