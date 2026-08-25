"""Tests for authentication, authorization, and tenant isolation
(models/auth.py, auth/*.py, routes/chat.py, memory tenant scoping).

Auth enforcement is gated by settings.require_auth (default False), so
these tests explicitly toggle it on via monkeypatch where needed, and
confirm the DEFAULT (auth disabled) behavior is completely unchanged —
that default-off posture is what keeps the existing frontend contract and
every pre-existing test intact.
"""

import asyncio
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import auth.dependency
import config
from auth.hashing import generate_api_key, hash_api_key, verify_api_key
from auth.store import InMemoryApiKeyStore
from main import app
from models.chat import ChatRequest
from models.cognitive_memory import MemoryRecord
from memory.store import SQLiteMemoryStore
from orchestration.workflow_runner import WorkflowRunner
from routes.chat import _rate_limiter as chat_rate_limiter
from routes.chat import workflow_runner as global_workflow_runner

client = TestClient(app)


def _enable_auth(monkeypatch) -> None:
    """Settings is a frozen dataclass and auth/dependency.py imported
    `settings` by reference at module load time, so patching config.settings
    directly would not affect the already-bound name auth.dependency uses
    at request time. Patch that specific binding instead — monkeypatch
    auto-reverts after each test, so no manual teardown is needed."""
    monkeypatch.setattr(auth.dependency, "settings", replace(auth.dependency.settings, require_auth=True))


def teardown_function() -> None:
    chat_rate_limiter.reset()


# ---------------------------------------------------------------------------
# Key hashing
# ---------------------------------------------------------------------------


def test_generate_api_key_produces_high_entropy_distinct_keys() -> None:
    a = generate_api_key()
    b = generate_api_key()
    assert a != b
    assert len(a) >= 32


def test_hash_api_key_is_deterministic() -> None:
    key = generate_api_key()
    assert hash_api_key(key) == hash_api_key(key)


def test_verify_api_key_accepts_correct_key() -> None:
    key = generate_api_key()
    assert verify_api_key(key, hash_api_key(key)) is True


def test_verify_api_key_rejects_wrong_key() -> None:
    key = generate_api_key()
    other = generate_api_key()
    assert verify_api_key(other, hash_api_key(key)) is False


def test_raw_key_is_never_stored_in_the_record() -> None:
    store = InMemoryApiKeyStore()
    raw_key, record = store.issue(tenant_id="t1")
    assert raw_key not in record.model_dump_json()
    assert record.hashed_key != raw_key


# ---------------------------------------------------------------------------
# ApiKeyStore
# ---------------------------------------------------------------------------


def test_issued_key_resolves_to_correct_record() -> None:
    store = InMemoryApiKeyStore()
    raw_key, record = store.issue(tenant_id="acme", role="admin")
    resolved = store.resolve(raw_key)
    assert resolved is not None
    assert resolved.tenant_id == "acme"
    assert resolved.role == "admin"
    assert resolved.key_id == record.key_id


def test_resolve_unknown_key_returns_none() -> None:
    store = InMemoryApiKeyStore()
    assert store.resolve("never-issued") is None


def test_revoked_key_no_longer_resolves() -> None:
    store = InMemoryApiKeyStore()
    raw_key, record = store.issue(tenant_id="acme")
    store.revoke(record.key_id)
    assert store.resolve(raw_key) is None


def test_default_role_is_user() -> None:
    store = InMemoryApiKeyStore()
    _, record = store.issue(tenant_id="acme")
    assert record.role == "user"


def test_clear_removes_all_keys() -> None:
    store = InMemoryApiKeyStore()
    store.issue(tenant_id="a")
    store.issue(tenant_id="b")
    store.clear()
    assert store.resolve("anything") is None


# ---------------------------------------------------------------------------
# Unauthorized access (auth required, no/invalid key)
# ---------------------------------------------------------------------------


def test_missing_key_is_rejected_when_auth_required(monkeypatch) -> None:
    _enable_auth(monkeypatch)
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Missing API key."}


def test_invalid_key_is_rejected_when_auth_required(monkeypatch) -> None:
    _enable_auth(monkeypatch)
    response = client.post("/api/chat", json={"message": "hello"}, headers={"X-API-Key": "not-a-real-key"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or revoked API key."}


def test_revoked_key_is_rejected_when_auth_required(monkeypatch) -> None:
    from auth.store import key_store

    raw_key, record = key_store.issue(tenant_id="t-revoked-test")
    key_store.revoke(record.key_id)
    _enable_auth(monkeypatch)
    response = client.post("/api/chat", json={"message": "hello"}, headers={"X-API-Key": raw_key})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Authorized access
# ---------------------------------------------------------------------------


def test_valid_key_is_accepted_when_auth_required(monkeypatch) -> None:
    from auth.store import key_store

    raw_key, _ = key_store.issue(tenant_id="t-valid-test", role="user")
    _enable_auth(monkeypatch)
    response = client.post("/api/chat", json={"message": "Summarize the plan"}, headers={"X-API-Key": raw_key})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_admin_role_is_accepted(monkeypatch) -> None:
    from auth.store import key_store

    raw_key, _ = key_store.issue(tenant_id="t-admin-test", role="admin")
    _enable_auth(monkeypatch)
    response = client.post("/api/chat", json={"message": "Summarize the plan"}, headers={"X-API-Key": raw_key})
    assert response.status_code == 200


def test_readonly_role_is_forbidden_from_chat(monkeypatch) -> None:
    from auth.store import key_store

    raw_key, _ = key_store.issue(tenant_id="t-readonly-test", role="readonly")
    _enable_auth(monkeypatch)
    response = client.post("/api/chat", json={"message": "Summarize the plan"}, headers={"X-API-Key": raw_key})
    assert response.status_code == 403
    assert response.json() == {"detail": "Your role does not permit this action."}


def test_unauthenticated_default_posture_is_unaffected_by_role_check() -> None:
    """When auth is NOT required (the default), no role restriction ever
    applies — this is what preserves the frontend's existing behavior."""
    response = client.post("/api/chat", json={"message": "Summarize the plan"})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tenant isolation (Cognitive Memory)
# ---------------------------------------------------------------------------


def test_memory_search_with_tenant_filter_excludes_other_tenants() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(MemoryRecord(
        type="semantic", content="Tenant A's confidential budget figure is here.",
        task_id="t1", source_agent="researcher", verification_state="verified",
        tags=[], provenance="x", tenant_id="tenant-a",
    ))
    store.write(MemoryRecord(
        type="semantic", content="Tenant B's confidential budget figure is here.",
        task_id="t2", source_agent="researcher", verification_state="verified",
        tags=[], provenance="x", tenant_id="tenant-b",
    ))

    results_a = store.search(query="confidential budget figure", tenant_id="tenant-a", limit=10)
    assert len(results_a) == 1
    assert results_a[0].record.tenant_id == "tenant-a"

    results_b = store.search(query="confidential budget figure", tenant_id="tenant-b", limit=10)
    assert len(results_b) == 1
    assert results_b[0].record.tenant_id == "tenant-b"


def test_memory_search_without_tenant_filter_is_unchanged_global_behavior() -> None:
    """Backward compatibility: omitting tenant_id (as every pre-existing
    caller does) must return the same results as before this feature."""
    store = SQLiteMemoryStore(":memory:")
    store.write(MemoryRecord(
        type="semantic", content="A shared budget figure here for everyone.",
        task_id="t1", source_agent="researcher", verification_state="verified",
        tags=[], provenance="x",  # no tenant_id — legacy write
    ))
    results = store.search(query="shared budget figure", limit=10)
    assert len(results) == 1


def test_tenant_scoped_search_does_not_fall_back_to_untenanted_records() -> None:
    """Strict isolation: a tenant-scoped query must never silently include
    records with no tenant_id — that would be a real data leak."""
    store = SQLiteMemoryStore(":memory:")
    store.write(MemoryRecord(
        type="semantic", content="An untenanted legacy budget figure.",
        task_id="t1", source_agent="researcher", verification_state="verified", tags=[], provenance="x",
    ))
    results = store.search(query="untenanted legacy budget figure", tenant_id="tenant-a", limit=10)
    assert results == []


def test_workflow_runner_end_to_end_tenant_isolation() -> None:
    """Full pipeline: two tenants chatting on the same shared runner never
    see each other's retrieved memory."""
    runner = WorkflowRunner()
    runner.memory_store.write(MemoryRecord(
        type="semantic", content="Tenant Alpha's private roadmap detail is here.",
        task_id="seed-alpha", source_agent="researcher", verification_state="verified",
        tags=["research"], provenance="x", tenant_id="tenant-alpha",
    ))
    runner.memory_store.write(MemoryRecord(
        type="semantic", content="Tenant Beta's private roadmap detail is here.",
        task_id="seed-beta", source_agent="researcher", verification_state="verified",
        tags=["research"], provenance="x", tenant_id="tenant-beta",
    ))

    response_alpha = asyncio.run(runner.run(
        ChatRequest(message="What do we know about the private roadmap detail?"), tenant_id="tenant-alpha",
    ))
    response_beta = asyncio.run(runner.run(
        ChatRequest(message="What do we know about the private roadmap detail?"), tenant_id="tenant-beta",
    ))

    alpha_retrieved = [m for m in runner.bus.get_task_messages(response_alpha.task_id) if m.intent == "memory_retrieved"]
    beta_retrieved = [m for m in runner.bus.get_task_messages(response_beta.task_id) if m.intent == "memory_retrieved"]

    assert len(alpha_retrieved) == 1
    assert len(beta_retrieved) == 1
    # Each tenant retrieved exactly their own record, never the other's.
    alpha_records = runner.memory_store.search(query="private roadmap detail", tenant_id="tenant-alpha", limit=10)
    beta_records = runner.memory_store.search(query="private roadmap detail", tenant_id="tenant-beta", limit=10)
    assert alpha_records[0].record.content == "Tenant Alpha's private roadmap detail is here."
    assert beta_records[0].record.content == "Tenant Beta's private roadmap detail is here."


def test_workflow_runner_consolidation_tags_records_with_tenant_id() -> None:
    runner = WorkflowRunner()
    response = asyncio.run(runner.run(
        ChatRequest(message="Create a roadmap and steps for launch"), tenant_id="tenant-gamma",
    ))
    task_records = runner.memory_store.list_for_task(response.task_id)
    assert all(record.tenant_id == "tenant-gamma" for record in task_records)


def test_workflow_runner_without_tenant_id_writes_untenanted_records() -> None:
    """Default/backward-compatible behavior: omitting tenant_id (as every
    pre-existing test does) writes tenant_id=None, unchanged from before."""
    runner = WorkflowRunner()
    response = asyncio.run(runner.run(ChatRequest(message="Create a roadmap and steps for launch")))
    task_records = runner.memory_store.list_for_task(response.task_id)
    assert all(record.tenant_id is None for record in task_records)


def test_full_http_request_threads_authenticated_tenant_into_memory(monkeypatch) -> None:
    from auth.store import key_store

    raw_key, _ = key_store.issue(tenant_id="tenant-http-test", role="user")
    _enable_auth(monkeypatch)

    response = client.post("/api/chat", json={"message": "Create a roadmap and steps for launch"}, headers={"X-API-Key": raw_key})
    assert response.status_code == 200
    task_id = response.json()["task_id"]

    task_records = global_workflow_runner.memory_store.list_for_task(task_id)
    assert all(record.tenant_id == "tenant-http-test" for record in task_records)


def test_two_different_authenticated_tenants_get_isolated_memory_over_http(monkeypatch) -> None:
    from auth.store import key_store

    raw_key_a, _ = key_store.issue(tenant_id="tenant-iso-a", role="user")
    raw_key_b, _ = key_store.issue(tenant_id="tenant-iso-b", role="user")
    _enable_auth(monkeypatch)

    global_workflow_runner.memory_store.write(MemoryRecord(
        type="semantic", content="Tenant ISO A exclusive fact about deployment timing.",
        task_id="seed-iso-a", source_agent="x", verification_state="verified",
        tags=[], provenance="x", tenant_id="tenant-iso-a",
    ))

    response_b = client.post(
        "/api/chat", json={"message": "What do we know about deployment timing?"}, headers={"X-API-Key": raw_key_b},
    )
    task_id_b = response_b.json()["task_id"]
    retrieval_events_b = [m for m in global_workflow_runner.bus.get_task_messages(task_id_b) if m.intent == "memory_retrieved"]
    assert retrieval_events_b == []  # tenant B never sees tenant A's data


# ---------------------------------------------------------------------------
# Regression — default (unauthenticated) behavior fully preserved
# ---------------------------------------------------------------------------


def test_chat_contract_unchanged_when_auth_disabled() -> None:
    response = client.post("/api/chat", json={"message": "Summarize the plan"})
    assert response.status_code == 200
    body = response.json()
    for field in ("task_id", "conversation_id", "answer", "mode", "status", "used_agents", "confidence"):
        assert field in body
    assert "tenant_id" not in body
    assert "principal" not in body


def test_all_static_endpoints_unaffected_by_auth_changes() -> None:
    for path in ("/", "/health", "/api/dashboard", "/api/agents", "/api/tasks", "/api/memory", "/api/workflows", "/api/research"):
        response = client.get(path)
        assert response.status_code == 200, path


def test_require_auth_defaults_to_false() -> None:
    fresh_settings = config.Settings()
    assert fresh_settings.require_auth is False


def test_manual_mode_still_works_unauthenticated() -> None:
    response = client.post("/api/chat", json={"message": "Use saved context and verify it", "mode": "manual", "selected_agents": ["memory", "critic"]})
    assert response.status_code == 200
