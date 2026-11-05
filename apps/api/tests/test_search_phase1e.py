"""Phase 1E: global search endpoint.

Every store the search route reads is monkeypatched to a fresh in-memory
instance — tests seed ONLY throwaway stores and never touch the real app.
Covers: validation bounds, prefix/word-boundary ranking, grouped results
across all eight sources, deep-link hrefs, snippets from message/memory
content, tenant isolation, parameter redaction and the global limit.
"""

import types

import pytest
from fastapi.testclient import TestClient

import memory.schedule_store as schedule_store_mod
import memory.task_store as task_store_mod
import memory.workflow_store as workflow_store_mod
import routes.chat as chat_routes
import services.approval_service as approval_service_mod
from main import app
from memory.alert_store import AlertStore
from memory.approval_store import ApprovalStore
from memory.conversation_store import ConversationStore
from memory.schedule_store import new_schedule
from memory.store import SQLiteMemoryStore
from models.cognitive_memory import MemoryRecord
from models.tasks import Task


@pytest.fixture
def env(monkeypatch):
    task_store = task_store_mod.SQLiteTaskStore(":memory:")
    workflow_store = workflow_store_mod.SQLiteWorkflowStore(":memory:")
    schedule_store = schedule_store_mod.SQLiteScheduleStore(":memory:")
    approval_service = approval_service_mod.ApprovalService(ApprovalStore(":memory:"))
    memory_store = SQLiteMemoryStore(":memory:")
    conversation_store = ConversationStore(":memory:")
    alert_store = AlertStore(":memory:")

    monkeypatch.setattr(task_store_mod, "get_default_task_store", lambda: task_store)
    monkeypatch.setattr(
        workflow_store_mod, "get_default_workflow_store", lambda: workflow_store
    )
    monkeypatch.setattr(
        schedule_store_mod, "get_default_schedule_store", lambda: schedule_store
    )
    monkeypatch.setattr(approval_service_mod, "get_approval_service", lambda: approval_service)
    monkeypatch.setattr(chat_routes, "alert_store", alert_store)
    monkeypatch.setattr(chat_routes, "conversation_store", conversation_store)
    monkeypatch.setattr(
        chat_routes, "workflow_runner", types.SimpleNamespace(memory_store=memory_store)
    )

    yield types.SimpleNamespace(
        client=TestClient(app),
        task_store=task_store,
        workflow_store=workflow_store,
        schedule_store=schedule_store,
        approval_service=approval_service,
        memory_store=memory_store,
        conversation_store=conversation_store,
        alert_store=alert_store,
    )


def _task(store, id_, title, agent="researcher", status="completed"):
    store.create(
        Task(
            id=id_, title=title, agent=agent, status=status,
            confidence=90, created="2026-01-01T00:00:00+00:00",
        )
    )


def test_query_length_bounds(env):
    assert env.client.get("/api/search", params={"q": "a"}).status_code == 422
    assert env.client.get("/api/search", params={"q": "x" * 101}).status_code == 422
    assert env.client.get("/api/search", params={"q": "ab"}).status_code == 200


def test_grouped_results_across_all_sources(env):
    _task(env.task_store, "task-1", "Quarterly revenue report")
    env.workflow_store.create(
        workflow_store_mod.WorkflowRecord(
            id="wf-1", name="Quarterly digest", description="Compile numbers",
            created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
        )
    )
    env.memory_store.write(
        MemoryRecord(
            type="semantic", content="Quarterly figures look solid",
            task_id="manual-test", source_agent="test", verification_state="unverified",
            provenance="test-seed",
        )
    )
    env.conversation_store.save_user_message(
        "conv-1", "Talk me through the quarterly numbers", title="Quarterly planning"
    )
    env.alert_store.create(
        title="Quarterly report finished", description="Task done",
        category="task", tone="success", link="/tasks?open=task-1",
    )
    env.schedule_store.create(
        new_schedule(
            name="Quarterly cleanup", tool="files.delete", parameters={},
            interval_seconds=3600, tenant_id="default",
        )
    )
    env.approval_service.store.create(
        task_id="task-1", tenant_id="default", requested_by_key_id=None,
        tool="quarterly-sync-tool", parameters={}, ttl_seconds=120,
    )

    body = env.client.get("/api/search", params={"q": "quarterly"}).json()
    groups = body["groups"]
    assert {"tasks", "approvals", "workflows", "memory", "conversations", "alerts", "schedules"} <= set(groups)
    assert groups["tasks"][0]["href"] == "/tasks?open=task-1"
    assert groups["conversations"][0]["href"] == "/chat?c=conv-1"
    assert groups["alerts"][0]["href"] == "/tasks?open=task-1"  # real link wins
    assert groups["schedules"][0]["href"] == "/desktop"
    assert body["total"] == sum(len(v) for v in groups.values())


def test_agents_are_searchable(env):
    body = env.client.get("/api/search", params={"q": "planner"}).json()
    agents = body["groups"].get("agents", [])
    assert agents and agents[0]["href"].startswith("/agents?open=")


def test_prefix_and_word_boundary_outrank_substring(env):
    _task(env.task_store, "task-a", "Allocation prime")   # word-prefix
    _task(env.task_store, "task-b", "Realloc task")       # substring only
    groups = env.client.get("/api/search", params={"q": "alloc"}).json()["groups"]
    ids = [r["id"] for r in groups["tasks"]]
    assert ids == ["task-a", "task-b"]
    assert groups["tasks"][0]["score"] > groups["tasks"][1]["score"]


def test_memory_and_conversation_snippets_come_from_content(env):
    env.memory_store.write(
        MemoryRecord(
            type="episodic", content="The client prefers pineapple sliders",
            task_id="manual-test", source_agent="test", verification_state="unverified",
            provenance="test-seed",
        )
    )
    env.conversation_store.save_user_message("conv-9", "Order pineapple sliders", title="Lunch")
    groups = env.client.get("/api/search", params={"q": "pineapple"}).json()["groups"]
    assert "pineapple" in groups["memory"][0]["snippet"].lower()
    assert "pineapple" in groups["conversations"][0]["snippet"].lower()


def test_tenant_isolation(env):
    _task(env.task_store, "task-mine", "Zephyr status board")
    env.approval_service.store.create(
        task_id="t", tenant_id="other-tenant", requested_by_key_id=None,
        tool="zephyr-secret-tool", parameters={}, ttl_seconds=60,
    )
    env.schedule_store.create(
        new_schedule(
            name="Zephyr other-tenant job", tool="files.read", parameters={},
            interval_seconds=60, tenant_id="other-tenant",
        )
    )
    groups = env.client.get("/api/search", params={"q": "zephyr"}).json()["groups"]
    ids = {r["id"] for rows in groups.values() for r in rows}
    assert "task-mine" in ids
    assert "zephyr-secret-tool" not in " ".join(
        r["title"] for rows in groups.values() for r in rows
    )
    assert all(
        r["id"] != "Zephyr other-tenant job" for rows in groups.values() for r in rows
    )
    # The other tenant's rows exist — they are simply invisible here.
    assert env.approval_service.list_approvals(tenant_id="other-tenant")
    assert env.schedule_store.list_all("other-tenant")


def test_search_never_returns_approval_parameters(env):
    env.approval_service.store.create(
        task_id="t", tenant_id="default", requested_by_key_id=None,
        tool="files.write",
        parameters={"file_path": "/vault/quarterly-hidden.txt", "password": "hunter2"},
        ttl_seconds=120,
    )
    res = env.client.get("/api/search", params={"q": "files"})
    assert res.status_code == 200
    raw = res.text
    assert "hunter2" not in raw
    assert "/vault/quarterly-hidden.txt" not in raw
    assert "parameters" not in raw


def test_global_limit_applies(env):
    for i in range(8):
        _task(env.task_store, f"task-{i}", f"Bundled widget {i}")
    body = env.client.get("/api/search", params={"q": "bundled", "limit": 3}).json()
    assert body["total"] == 3
    assert sum(len(v) for v in body["groups"].values()) == 3


def test_no_matches_is_an_honest_empty_result(env):
    _task(env.task_store, "task-1", "Real work")
    body = env.client.get("/api/search", params={"q": "qqzznothing"}).json()
    assert body["groups"] == {}
    assert body["total"] == 0
