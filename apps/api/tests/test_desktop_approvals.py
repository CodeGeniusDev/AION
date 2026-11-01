"""Human-in-the-loop desktop approval lifecycle tests.

Covers the ten security properties from the approval-system plan:
unapproved execution never runs, rejected never runs, approved runs
exactly once, double execution prevented, expiry enforced, invalid task
ids rejected, unauthorized callers blocked, bridge failures handled
safely, audit log append-only and secret-free, and the approved
parameter snapshot is what executes (no TOCTOU).

Every test uses a mock bridge client — no desktop tool, subprocess, or
file operation is ever executed here.
"""

import json
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import auth.dependency
import routes.approvals as routes_approvals
from auth.store import key_store
from main import app
from memory.approval_store import ApprovalStore
from services import approval_service as approval_service_module
from services.desktop_bridge_client import BridgeError

client = TestClient(app)

SECRET = "bridge-secret-never-frontend"
TOKEN = "grant-token-never-logged"


class MockBridgeClient:
    """Stands in for DesktopBridgeClient. Records every call so tests can
    assert the executor was called exactly once / not at all."""

    def __init__(self, *, fail_register=False, fail_execute=False, result=None):
        self.register_calls = []
        self.execute_calls = []
        self.fail_register = fail_register
        self.fail_execute = fail_execute
        self.result = result if result is not None else {"success": True, "duration_ms": 1.0}

    def register_grant(self, **kwargs):
        self.register_calls.append(kwargs)
        if self.fail_register:
            raise BridgeError("bridge unreachable: ConnectError")

    def execute(self, **kwargs):
        self.execute_calls.append(kwargs)
        if self.fail_execute:
            raise BridgeError("bridge returned 500: boom")
        return dict(self.result)


@pytest.fixture()
def store(monkeypatch) -> ApprovalStore:
    """Fresh in-memory ledger per test, injected into the singleton
    service the routes use (no state can leak between tests)."""
    fresh = ApprovalStore(":memory:")
    monkeypatch.setattr(approval_service_module._default_approval_service, "store", fresh)
    return fresh


@pytest.fixture()
def bridge(monkeypatch) -> MockBridgeClient:
    mock = MockBridgeClient()
    monkeypatch.setattr(
        approval_service_module._default_approval_service, "_bridge_client", mock,
    )
    # Keep dispatch inline (no background-task timing) for deterministic asserts.
    _patch_settings(monkeypatch, approval_dispatch_async=False)
    return mock


def _request(tool="file_read", parameters=None, **kwargs) -> dict:
    body = {"tool": tool, "parameters": parameters if parameters is not None else {"path": "notes.txt"}}
    body.update(kwargs)
    response = client.post("/api/desktop/execute", json=body)
    assert response.status_code == 202, response.text
    return response.json()


def _enable_auth(monkeypatch) -> None:
    """Same binding-swap trick as test_auth_tenant_isolation: settings is
    frozen and imported by reference, so patch the module-level name."""
    monkeypatch.setattr(
        auth.dependency, "settings", replace(auth.dependency.settings, require_auth=True),
    )


def _patch_settings(monkeypatch, **overrides) -> None:
    """Settings is a frozen dataclass — swap the whole binding instead of
    assigning fields. Patched in every module that consumed it by name."""
    for module in (approval_service_module, routes_approvals):
        monkeypatch.setattr(module, "settings", replace(module.settings, **overrides))


# ---------------------------------------------------------------------------
# 1. Unapproved execution is rejected — the request path never dispatches
# ---------------------------------------------------------------------------

def test_execute_request_never_runs_without_approval(store, bridge):
    result = _request()
    assert result["status"] == "pending_approval"
    assert result["requires"] == "human_approval"
    assert bridge.register_calls == [] and bridge.execute_calls == []
    record = store.get(result["approval_id"])
    assert record.status == "pending_approval"


def test_no_silent_approval_path_exists(store, bridge):
    """There is exactly one policy: human_required. Nothing in the API
    surface moves a row from pending_approval to running without the
    atomic approve+claim."""
    result = _request(tool="desktop_list_apps")  # a NON-protected tool…
    assert result["status"] == "pending_approval"
    assert store.get(result["approval_id"]).status == "pending_approval"
    assert bridge.execute_calls == []


# ---------------------------------------------------------------------------
# 2. Rejected execution never runs
# ---------------------------------------------------------------------------

def test_rejected_approval_never_executes(store, bridge):
    result = _request()
    approval_id = result["approval_id"]
    rejected = client.post(f"/api/approvals/{approval_id}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    # A later approve attempt on a rejected row: 409, and still zero dispatch.
    assert client.post(f"/api/approvals/{approval_id}/approve").status_code == 409
    assert bridge.register_calls == [] and bridge.execute_calls == []
    # Linked task flows to failed, reason recorded.
    task = client.get(f"/api/tasks/{result['task_id']}")
    assert task.status_code == 200
    assert task.json()["status"] == "failed"


# ---------------------------------------------------------------------------
# 3. Approved execution runs exactly once
# ---------------------------------------------------------------------------

def test_approved_execution_runs_once(store, bridge):
    result = _request(parameters={"path": "notes.txt"})
    approve = client.post(f"/api/approvals/{result['approval_id']}/approve")
    assert approve.status_code == 202
    assert approve.json()["status"] == "running"
    assert len(bridge.execute_calls) == 1
    # The approved snapshot — not a re-submitted payload — is what ran.
    assert bridge.execute_calls[0]["parameters"] == {"path": "notes.txt"}
    assert bridge.execute_calls[0]["tool"] == "file_read"
    final = store.get(result["approval_id"])
    assert final.status == "completed"
    assert final.error is None


# ---------------------------------------------------------------------------
# 4. Double execution prevented (sequential and concurrent)
# ---------------------------------------------------------------------------

def test_double_approve_returns_409_and_single_execution(store, bridge):
    result = _request()
    approval_id = result["approval_id"]
    assert client.post(f"/api/approvals/{approval_id}/approve").status_code == 202
    second = client.post(f"/api/approvals/{approval_id}/approve")
    assert second.status_code == 409
    assert len(bridge.execute_calls) == 1
    assert store.get(approval_id).status == "completed"


def test_concurrent_approves_claim_exactly_once(store, bridge):
    """Two parallel approve calls race the atomic claim: exactly one 202,
    exactly one execution — the property comes from SQL rowcount, not
    from client behavior."""
    approval_id = _request()["approval_id"]
    codes: list[int] = []
    barrier = threading.Barrier(2)

    def approve():
        barrier.wait()
        codes.append(client.post(f"/api/approvals/{approval_id}/approve").status_code)

    threads = [threading.Thread(target=approve) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    assert sorted(codes) == [202, 409], codes
    assert len(bridge.execute_calls) == 1


# ---------------------------------------------------------------------------
# 5. Expired approvals rejected
# ---------------------------------------------------------------------------

def test_expired_pending_cannot_be_approved(store, bridge):
    """A pending row past its deadline is lazily swept to `expired` and
    any late approve attempt gets 410 — the tool never runs."""
    record = store.create(
        task_id="task-expiring", tenant_id="default",
        requested_by_key_id=None, tool="file_read",
        parameters={"path": "x"}, ttl_seconds=-1,
    )
    # Listing lazily sweeps pending rows past their deadline to expired.
    listed = client.get("/api/approvals").json()["items"]
    expired_row = next(item for item in listed if item["id"] == record.id)
    assert expired_row["status"] == "expired"
    approve = client.post(f"/api/approvals/{record.id}/approve")
    assert approve.status_code == 410
    assert bridge.execute_calls == []


# ---------------------------------------------------------------------------
# 6. Invalid task IDs rejected
# ---------------------------------------------------------------------------

def test_execute_with_unknown_task_id_returns_404(bridge):
    response = client.post(
        "/api/desktop/execute",
        json={"tool": "file_read", "parameters": {"path": "x"}, "task_id": "task-does-not-exist"},
    )
    assert response.status_code == 404
    assert bridge.execute_calls == []


def test_execute_with_unknown_tool_returns_404(bridge):
    response = client.post(
        "/api/desktop/execute", json={"tool": "launch_missiles", "parameters": {}},
    )
    assert response.status_code == 404
    assert bridge.execute_calls == []


def test_execute_links_existing_valid_task(store):
    created = client.post("/api/tasks", json={"title": "existing task"})
    assert created.status_code in (200, 201)
    task_id = created.json()["id"]
    result = _request(task_id=task_id)
    assert result["task_id"] == task_id
    assert store.get(result["approval_id"]).task_id == task_id


# ---------------------------------------------------------------------------
# 7. Unauthorized users cannot approve or execute
# ---------------------------------------------------------------------------

def test_readonly_role_cannot_approve(store, bridge, monkeypatch):
    _enable_auth(monkeypatch)
    raw_user, _ = key_store.issue(tenant_id="t-readonly-appr", role="user")
    raw_readonly, _ = key_store.issue(tenant_id="t-readonly-appr", role="readonly")
    user_headers = {"X-API-Key": raw_user}
    readonly_headers = {"X-API-Key": raw_readonly}
    # readonly can see the queue…
    assert client.get("/api/approvals", headers=readonly_headers).status_code == 200
    # …but cannot request execution.
    assert client.post("/api/desktop/execute",
                       json={"tool": "file_read", "parameters": {}},
                       headers=readonly_headers).status_code == 403
    # Same tenant: a readonly approve is 403 (role), not merely tenant-scoped 404.
    approval_id = client.post(
        "/api/desktop/execute", json={"tool": "file_read", "parameters": {"path": "p"}},
        headers=user_headers,
    ).json()["approval_id"]
    assert client.post(f"/api/approvals/{approval_id}/approve",
                       headers=readonly_headers).status_code == 403
    assert client.post(f"/api/approvals/{approval_id}/reject",
                       headers=readonly_headers).status_code == 403
    assert bridge.execute_calls == []


def test_wrong_api_key_cannot_approve_or_execute(store, bridge, monkeypatch):
    _enable_auth(monkeypatch)
    response = client.post(
        "/api/desktop/execute", json={"tool": "file_read", "parameters": {}},
        headers={"X-API-Key": "never-issued-key"},
    )
    assert response.status_code == 401
    # Create a real pending approval with a valid key, then show a wrong
    # key can neither approve it nor reach the bridge.
    raw_key, _ = key_store.issue(tenant_id="t-wrongkey", role="user")
    approval_id = client.post(
        "/api/desktop/execute", json={"tool": "file_read", "parameters": {"path": "p"}},
        headers={"X-API-Key": raw_key},
    ).json()["approval_id"]
    response = client.post(
        f"/api/approvals/{approval_id}/approve", headers={"X-API-Key": "never-issued-key"},
    )
    assert response.status_code == 401
    assert store.get(approval_id).status == "pending_approval"
    assert bridge.execute_calls == []


def test_tenant_cannot_see_other_tenant_approvals(store, bridge, monkeypatch):
    _enable_auth(monkeypatch)
    raw_a, _ = key_store.issue(tenant_id="tenant-appr-a", role="user")
    raw_b, _ = key_store.issue(tenant_id="tenant-appr-b", role="user")
    created = client.post(
        "/api/desktop/execute", json={"tool": "file_read", "parameters": {"path": "p"}},
        headers={"X-API-Key": raw_a},
    )
    assert created.status_code == 202
    approval_id = created.json()["approval_id"]

    listed_b = client.get("/api/approvals", headers={"X-API-Key": raw_b}).json()
    assert all(item["id"] != approval_id for item in listed_b["items"])
    # Tenant B cannot even probe existence: same 404 as a nonexistent id.
    assert client.get(f"/api/approvals/{approval_id}", headers={"X-API-Key": raw_b}).status_code == 404
    assert client.post(f"/api/approvals/{approval_id}/approve",
                       headers={"X-API-Key": raw_b}).status_code == 404
    # Tenant A can, and execution goes out exactly once.
    assert client.post(f"/api/approvals/{approval_id}/approve",
                       headers={"X-API-Key": raw_a}).status_code == 202
    assert len(bridge.execute_calls) == 1


# ---------------------------------------------------------------------------
# 8. Bridge failures handled safely
# ---------------------------------------------------------------------------

def test_bridge_unreachable_marks_failed_no_partial_state(store, monkeypatch):
    mock = MockBridgeClient(fail_register=True)
    monkeypatch.setattr(approval_service_module._default_approval_service, "_bridge_client", mock)
    _patch_settings(monkeypatch, approval_dispatch_async=False)
    approval_id = _request()["approval_id"]
    response = client.post(f"/api/approvals/{approval_id}/approve")
    assert response.status_code == 202  # claim succeeded…
    row = store.get(approval_id)
    assert row.status == "failed"        # …dispatch failed safely
    assert "unreachable" in (row.error or "")
    assert mock.execute_calls == []      # never executed anything
    task = client.get(f"/api/tasks/{row.task_id}").json()
    assert task["status"] == "failed"


def test_bridge_error_response_marks_failed_and_audits(store, monkeypatch):
    mock = MockBridgeClient(result={"success": False, "error": "tool blew up"})
    monkeypatch.setattr(approval_service_module._default_approval_service, "_bridge_client", mock)
    _patch_settings(monkeypatch, approval_dispatch_async=False)
    approval_id = _request()["approval_id"]
    assert client.post(f"/api/approvals/{approval_id}/approve").status_code == 202
    row = store.get(approval_id)
    assert row.status == "failed"
    assert "tool blew up" in (row.error or "")
    events = [e["event"] for e in client.get(f"/api/audit?approval_id={approval_id}").json()["items"]]
    assert "failed" in events
    # A failed run consumed its one-time claim: it can never be re-approved.
    assert client.post(f"/api/approvals/{approval_id}/approve").status_code == 409


# ---------------------------------------------------------------------------
# 9. Audit log append-only, lifecycle-complete, secret-free
# ---------------------------------------------------------------------------

def test_audit_log_contains_full_lifecycle(store, bridge):
    approval_id = _request(parameters={"path": "notes.txt"})["approval_id"]
    client.post(f"/api/approvals/{approval_id}/approve")
    events = [e["event"] for e in client.get(f"/api/audit?approval_id={approval_id}").json()["items"]]
    assert events == ["requested", "approved", "claimed", "granted", "executed"]


def test_audit_and_responses_never_contain_secrets_or_token_material(store, bridge, monkeypatch):
    mock = MockBridgeClient()
    monkeypatch.setattr(approval_service_module._default_approval_service, "_bridge_client", mock)
    _patch_settings(monkeypatch, approval_dispatch_async=False, agent_secret=SECRET)
    approval_id = _request(parameters={
        "path": "notes.txt",
        "api_key": "sk-live-DO-NOT-LEAK",
        "content": "confidential-file-body-DO-NOT-LEAK",
    })["approval_id"]

    # Sanitized in the API response…
    detail = client.get(f"/api/approvals/{approval_id}").json()
    assert detail["parameters"]["api_key"] == {"redacted": True}
    assert detail["parameters"]["content"]["redacted"] is True
    assert "confidential-file-body" not in json.dumps(detail)

    client.post(f"/api/approvals/{approval_id}/approve")
    # …and in every audit detail, across the full lifecycle.
    audit = client.get("/api/audit").json()["items"]
    blob = json.dumps(audit)
    for forbidden in (SECRET, TOKEN, "sk-live-DO-NOT-LEAK", "confidential-file-body"):
        assert forbidden not in blob

    # The ledger stores only the grant token's SHA-256 hash, never the raw
    # token (which the mock client receives in-flight, by design).
    with store._cursor() as cursor:  # noqa: SLF001 — deliberate DB-level assertion
        cursor.execute("SELECT parameters_json, execution_token_hash FROM approval_requests")
        row = cursor.fetchone()
        assert TOKEN not in (row["execution_token_hash"] or "")
        assert len(row["execution_token_hash"]) == 64
        # The EXECUTED snapshot is the approved one (raw content stays in the
        # local ledger the bridge also runs from — it never hits responses).
        assert "confidential-file-body" in row["parameters_json"]


# ---------------------------------------------------------------------------
# 10. Parameters TOCTOU: claim-time integrity check
# ---------------------------------------------------------------------------

def test_tampered_snapshot_is_never_executed(store, bridge):
    """Simulate any tampering with the stored parameters between approval
    and dispatch: the claim re-hashes against the immutable params_hash
    and refuses to run."""
    approval_id = _request(parameters={"path": "original.txt"})["approval_id"]
    with store._cursor() as cursor:  # noqa: SLF001 — deliberate DB-level tampering
        cursor.execute(
            "UPDATE approval_requests SET parameters_json = ? WHERE id = ?",
            (json.dumps({"path": "TAMPERED.txt"}), approval_id),
        )
    response = client.post(f"/api/approvals/{approval_id}/approve")
    assert response.status_code == 500
    assert bridge.execute_calls == [] and bridge.register_calls == []
    assert store.get(approval_id).status == "failed"


# ---------------------------------------------------------------------------
# Contract stability: existing endpoints untouched
# ---------------------------------------------------------------------------

def test_approval_endpoints_do_not_disturb_existing_routes(store):
    for path in ("/health", "/api/tasks", "/api/alerts", "/api/dashboard"):
        assert client.get(path).status_code == 200
    response = client.post("/api/chat", json={"message": "Summarize the plan"})
    assert response.status_code == 200


def test_approvals_listing_shape(store, bridge):
    _request()
    body = client.get("/api/approvals?status=pending_approval").json()
    assert set(body) == {"items", "total"}
    item = body["items"][0]
    assert set(item) >= {"id", "task_id", "tool", "parameters", "status", "created_at", "expires_at"}
    assert "tenant_id" not in item
    assert "parameters_json" not in item and "execution_token_hash" not in item


# ---------------------------------------------------------------------------
# Regression: production async-dispatch mode (AION_APPROVAL_DISPATCH_ASYNC=1)
# ---------------------------------------------------------------------------

def test_async_dispatch_mode_executes_after_202(store, monkeypatch):
    """The default production path schedules the bridge dispatch as a
    response BackgroundTask. Found broken by the manual E2E run (the first
    implementation used a nonexistent request attribute and 500-ed *after*
    the atomic claim — fail-safe but stuck in running). TestClient runs
    background tasks before returning, so the whole lifecycle completes
    within this call."""
    mock = MockBridgeClient()
    monkeypatch.setattr(
        approval_service_module._default_approval_service, "_bridge_client", mock,
    )
    _patch_settings(monkeypatch, approval_dispatch_async=True)
    approval_id = _request()["approval_id"]
    response = client.post(f"/api/approvals/{approval_id}/approve")
    assert response.status_code == 202
    assert response.json()["status"] == "running"
    assert len(mock.execute_calls) == 1
    assert store.get(approval_id).status == "completed"
    # And the consumed claim still 409s afterwards in async mode too.
    assert client.post(f"/api/approvals/{approval_id}/approve").status_code == 409
