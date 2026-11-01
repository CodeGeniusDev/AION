"""Phase 1 — Real Workflow entity.

Covers the SQLite store (schema, one-time seed, atomic run claim, stale
recovery), the service layer (model-safe agent whitelist, create/get, real
run via WorkflowRunner), and the HTTP endpoints (backward-compatible list
shape, create, run, error codes). Model calls are disabled process-wide by
conftest, so runs exercise the real runner in development mode without any
network.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import memory.workflow_store as workflow_store_module
import services.workflows_service as workflows_service
from main import app
from memory.workflow_store import SQLiteWorkflowStore, WorkflowRecord
from models.chat import ChatResponse
from models.workflows import WorkflowCreateRequest

client = TestClient(app)


class _FakeRunner:
    """Records the ChatRequest it is given and returns a canned response, so
    run-path tests assert the workflow executes in manual mode with ONLY the
    model-safe agent ids and nothing else."""

    def __init__(self, *, status="completed", error=None):
        self.status = status
        self.error = error
        self.requests = []

    async def run(self, request, available_memory=None, tenant_id=None):
        self.requests.append(request)
        return ChatResponse(
            task_id="task-run-0001",
            conversation_id="conv-0001",
            answer="ok" if self.status == "completed" else "nope",
            mode=request.mode,
            status=self.status,
            used_agents=[],
            confidence=0.7,
            processing_time_ms=12,
            selection_summary="manual run",
            error=self.error,
        )


def _record(**overrides) -> WorkflowRecord:
    now = datetime.now(timezone.utc).isoformat()
    base = dict(
        id="wf-test0001", name="Test Flow", description="d",
        agents=["Planner", "Critic"], agent_ids=["planner", "critic"],
        runs=0, state="Ready", created_at=now, updated_at=now,
    )
    base.update(overrides)
    return WorkflowRecord(**base)


@pytest.fixture()
def store(tmp_path):
    return SQLiteWorkflowStore(str(tmp_path / "wf.db"))


@pytest.fixture()
def isolate_default_store():
    """Point the process-wide default store at a throwaway in-memory DB for
    endpoint tests, then restore a fresh one so no other test is affected."""
    workflow_store_module._default_store = SQLiteWorkflowStore(":memory:")
    yield
    workflow_store_module._default_store = None


# ---------------------------------------------------------------------------
# Store: schema + one-time seed + idempotency
# ---------------------------------------------------------------------------


def test_seeds_three_demo_workflows_once(store):
    ids = {w.id for w in store.list_all()}
    assert ids == {"deep-research", "decision-brief", "knowledge-capture"}
    # Counters start real (0), not the old fake demo numbers.
    assert all(w.runs == 0 for w in store.list_all())


def test_seed_is_idempotent_across_reopen(tmp_path):
    db = str(tmp_path / "wf.db")
    SQLiteWorkflowStore(db)
    second = SQLiteWorkflowStore(db)  # reopen same file
    assert len(second.list_all()) == 3  # not re-seeded to 6


def test_seed_respects_deletions_on_reopen(tmp_path):
    db = str(tmp_path / "wf.db")
    first = SQLiteWorkflowStore(db)
    with first._cursor() as cursor:
        cursor.execute("DELETE FROM workflows WHERE id = 'deep-research'")
    second = SQLiteWorkflowStore(db)
    assert {w.id for w in second.list_all()} == {"decision-brief", "knowledge-capture"}


def test_list_shape_is_backward_compatible(store):
    for workflow in store.public_list():
        assert set(workflow.model_dump().keys()) == {"id", "name", "description", "agents", "runs", "state"}
        assert workflow.state in {"Ready", "Running"}
        assert isinstance(workflow.agents, list) and all(isinstance(a, str) for a in workflow.agents)


# ---------------------------------------------------------------------------
# Store: atomic claim + finish + stale recovery
# ---------------------------------------------------------------------------


def test_claim_increments_runs_and_blocks_second_claim(store):
    store.create(_record(id="wf-claim"))
    first = store.claim_for_run("wf-claim")
    assert first is not None and first.state == "Running" and first.runs == 1
    # A genuinely Running row cannot be claimed again.
    assert store.claim_for_run("wf-claim") is None


def test_finish_run_releases_claim_and_persists_task_id(store):
    store.create(_record(id="wf-finish"))
    store.claim_for_run("wf-finish")
    finished = store.finish_run("wf-finish", last_task_id="task-xyz", error=None)
    assert finished.state == "Ready"
    assert finished.last_task_id == "task-xyz"
    # Now claimable again.
    assert store.claim_for_run("wf-finish") is not None


def test_stale_running_reports_ready_and_is_reclaimable(store):
    old = (datetime.now(timezone.utc) - timedelta(seconds=workflow_store_module.RUNNING_STALE_SECONDS + 10)).isoformat()
    store.create(_record(id="wf-stale", state="Running", updated_at=old))
    pub = store.public_get("wf-stale")
    assert pub.state == "Ready"  # corrected on read
    assert store.claim_for_run("wf-stale") is not None


# ---------------------------------------------------------------------------
# Service: model-safe agent whitelist
# ---------------------------------------------------------------------------


def test_normalize_accepts_display_aliases():
    assert workflows_service.normalize_agents(["Planner", "Research", "Critic", "Memory"]) == [
        "planner", "researcher", "critic", "memory",
    ]


def test_normalize_rejects_unknown_agent():
    with pytest.raises(Exception) as exc:
        workflows_service.normalize_agents(["Planner", "desktop_open_app"])
    assert exc.value.status_code == 400


def test_normalize_rejects_non_model_safe_bridge_name():
    for bad in ["browser_navigate", "file_write", "desktop", "tool_system"]:
        with pytest.raises(Exception) as exc:
            workflows_service.normalize_agents([bad])
        assert exc.value.status_code == 400


def test_create_workflow_persists_canonical_ids(store):
    created = workflows_service.create_workflow(
        store, WorkflowCreateRequest(name="My Flow", description="x", agents=["Planner", "Critic"]),
    )
    record = store.get(created.id)
    assert record.agent_ids == ["planner", "critic"]
    assert record.agents == ["Planner", "Critic"]  # display preserved for the API


# ---------------------------------------------------------------------------
# Service: run through WorkflowRunner (manual mode, model-safe only)
# ---------------------------------------------------------------------------


def test_run_executes_in_manual_mode_with_only_safe_agents(store):
    created = workflows_service.create_workflow(
        store, WorkflowCreateRequest(name="Run Me", description="", agents=["Planner", "Memory"]),
    )
    runner = _FakeRunner()
    workflow, run = asyncio.run(workflows_service.run_workflow(store, runner, created.id, "hello"))

    assert runner.requests[0].mode == "manual"
    assert set(runner.requests[0].selected_agents) == {"planner", "memory"}
    assert workflow.runs == 1
    assert workflow.state == "Ready"
    assert run.status == "completed"
    assert store.get(created.id).last_task_id == "task-run-0001"


def test_run_increments_counter_even_on_failure(store):
    created = workflows_service.create_workflow(
        store, WorkflowCreateRequest(name="Fail Flow", description="", agents=["Critic"]),
    )
    runner = _FakeRunner(status="failed", error="boom")
    workflow, run = asyncio.run(workflows_service.run_workflow(store, runner, created.id, "hello"))
    assert workflow.runs == 1
    assert workflow.state == "Ready"
    assert run.status == "failed" and run.error == "boom"
    assert store.get(created.id).last_error == "boom"


def test_concurrent_run_is_refused(store):
    created = workflows_service.create_workflow(
        store, WorkflowCreateRequest(name="Busy", description="", agents=["Planner"]),
    )
    store.claim_for_run(created.id)  # simulate an in-flight run
    with pytest.raises(Exception) as exc:
        asyncio.run(workflows_service.run_workflow(store, _FakeRunner(), created.id, "hello"))
    assert exc.value.status_code == 409


def test_run_revalidates_persisted_agents(store):
    # A row whose agent_ids were tampered with outside the whitelist must
    # still be refused — the run path does not trust stored data blindly.
    bad = _record(id="wf-tampered", agent_ids=["planner", "desktop_open_app"])
    store.create(bad)
    with pytest.raises(Exception) as exc:
        asyncio.run(workflows_service.run_workflow(store, _FakeRunner(), "wf-tampered", "hello"))
    assert exc.value.status_code == 400


def test_run_unknown_workflow_is_404(store):
    with pytest.raises(Exception) as exc:
        asyncio.run(workflows_service.run_workflow(store, _FakeRunner(), "does-not-exist", "hi"))
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_endpoint_list_seeded_real_rows(isolate_default_store):
    body = client.get("/api/workflows").json()
    assert body["total"] == 3
    assert {"deep-research", "decision-brief", "knowledge-capture"} <= {w["id"] for w in body["items"]}
    assert all(w["runs"] == 0 for w in body["items"])


def test_endpoint_get_single(isolate_default_store):
    response = client.get("/api/workflows/deep-research")
    assert response.status_code == 200
    assert response.json()["name"] == "Deep Research"


def test_endpoint_get_unknown_404(isolate_default_store):
    assert client.get("/api/workflows/nope").status_code == 404


def test_endpoint_create_and_reject_bad_agent(isolate_default_store):
    ok = client.post("/api/workflows", json={"name": "New", "description": "", "agents": ["Planner"]})
    assert ok.status_code == 201
    assert ok.json()["runs"] == 0 and ok.json()["state"] == "Ready"

    bad = client.post("/api/workflows", json={"name": "X", "description": "", "agents": ["file_write"]})
    assert bad.status_code == 400


def test_endpoint_run_increments_counter_real_flow(isolate_default_store):
    created = client.post("/api/workflows", json={"name": "Run Flow", "description": "", "agents": ["Planner", "Critic"]}).json()
    before = created["runs"]
    response = client.post(f"/api/workflows/{created['id']}/run", json={"input": "summarize the plan"})
    assert response.status_code == 200
    body = response.json()
    assert body["workflow"]["runs"] == before + 1
    assert body["workflow"]["state"] == "Ready"
    # run block reflects the real (development-mode) runner response contract
    for field in ("task_id", "status", "answer", "confidence", "processing_time_ms"):
        assert field in body["run"]


def test_endpoint_run_rejects_empty_input(isolate_default_store):
    response = client.post("/api/workflows/deep-research/run", json={"input": ""})
    assert response.status_code == 422  # pydantic min_length on WorkflowRunRequest.input
