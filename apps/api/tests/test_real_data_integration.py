"""Tests confirming /api/agents, /api/tasks, /api/memory, /api/research,
/api/dashboard now serve real backend data (Agent Registry, Cognitive
Memory) instead of static demo data, while preserving their existing
response contracts. /api/chat and /api/workflows are explicitly out of
scope here: chat's contract is unchanged (covered by existing regression
tests), and workflows remains honest demo data (documented in
routes/workflows.py — no backend Workflow entity exists).
"""

from fastapi.testclient import TestClient

from main import app
from memory.store import SQLiteMemoryStore
from models.cognitive_memory import MemoryRecord
from routes.chat import workflow_runner as global_workflow_runner
from services.dashboard_service import get_dashboard
from services.memory_service import get_memory
from services.research_service import get_research
from services.tasks_service import get_tasks

client = TestClient(app)


# ---------------------------------------------------------------------------
# /api/agents — real Agent Registry
# ---------------------------------------------------------------------------


def test_agents_endpoint_reflects_real_registry_ids() -> None:
    response = client.get("/api/agents")
    body = response.json()
    assert {agent["id"] for agent in body["items"]} == {"planner", "researcher", "critic", "memory"}


def test_agents_endpoint_reflects_real_availability_status() -> None:
    """CriticAgent is declared STANDBY in its real Cognitive DNA identity
    (agents/critic.py) — confirm the API surfaces that real value."""
    response = client.get("/api/agents")
    body = response.json()
    critic = next(agent for agent in body["items"] if agent["id"] == "critic")
    assert critic["status"] == "standby"


def test_agents_confidence_is_a_real_derived_percentage() -> None:
    response = client.get("/api/agents")
    body = response.json()
    for agent in body["items"]:
        assert 0 <= agent["confidence"] <= 100


# ---------------------------------------------------------------------------
# /api/tasks — derived from real episodic memory
# ---------------------------------------------------------------------------


def test_tasks_service_derives_from_real_episodic_records() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(MemoryRecord(
        type="episodic",
        content="Task (auto mode) ran agents ['planner', 'researcher'] — some reason. Final status: completed.",
        task_id="t1", source_agent="aion", verification_state="unverified", tags=[], provenance="workflow_runner",
    ))
    result = get_tasks(store)
    assert result.total == 1
    assert result.items[0].agent == "planner"
    assert result.items[0].status == "completed"
    assert result.items[0].confidence == 100


def test_tasks_service_parses_failed_status_correctly() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(MemoryRecord(
        type="episodic",
        content="Task (auto mode) ran agents ['planner'] — reason. Final status: failed.",
        task_id="t2", source_agent="aion", verification_state="unverified", tags=[], provenance="workflow_runner",
    ))
    result = get_tasks(store)
    assert result.items[0].status == "failed"
    assert result.items[0].confidence == 0


def test_tasks_endpoint_end_to_end_reflects_real_chat_activity() -> None:
    client.post("/api/chat", json={"message": "Create a roadmap and steps for a new integration test project"})
    response = client.get("/api/tasks")
    body = response.json()
    assert body["total"] >= 1
    assert any("integration test project" in item["title"] or "planner" in item["agent"] for item in body["items"])


def test_single_task_endpoint_returns_a_real_task_by_real_id() -> None:
    client.post("/api/chat", json={"message": "Create a roadmap and steps for lookup verification"})
    listing = client.get("/api/tasks").json()
    real_id = listing["items"][0]["id"]
    response = client.get(f"/api/tasks/{real_id}")
    assert response.status_code == 200
    assert response.json()["id"] == real_id


def test_single_task_endpoint_404s_for_a_semantic_not_episodic_id() -> None:
    """A memory_id that exists but isn't an episodic task record must not
    be returned by the task-lookup endpoint."""
    global_workflow_runner.memory_store.write(MemoryRecord(
        type="semantic", content="Not a task record.", task_id="t3",
        source_agent="x", verification_state="verified", tags=[], provenance="x",
    ))
    semantic_id = global_workflow_runner.memory_store.list_recent(memory_type="semantic", limit=1)[0].memory_id
    response = client.get(f"/api/tasks/{semantic_id}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /api/memory — real counts
# ---------------------------------------------------------------------------


def test_memory_endpoint_counts_are_real_not_fixed_demo_values() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(MemoryRecord(
        type="semantic", content="A real fact.", task_id="t1", source_agent="x",
        verification_state="verified", tags=[], provenance="x",
    ))
    result = get_memory(store)
    semantic_category = next(c for c in result.categories if c.id == "semantic")
    assert semantic_category.count == "1 record"


def test_memory_endpoint_category_types_are_correctly_mapped() -> None:
    """Regression guard for a real bug caught during this integration pass:
    episodic was incorrectly mapped to type='vector' by a buggy ternary."""
    store = SQLiteMemoryStore(":memory:")
    result = get_memory(store)
    types_by_id = {category.id: category.type for category in result.categories}
    assert types_by_id["episodic"] == "short_term"
    assert types_by_id["semantic"] == "long_term"


# ---------------------------------------------------------------------------
# /api/research — real verified evidence only
# ---------------------------------------------------------------------------


def test_research_service_only_includes_research_tagged_records() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(MemoryRecord(
        type="semantic", content="A research finding.", task_id="t1", source_agent="x",
        verification_state="verified", tags=["research"], provenance="x",
    ))
    store.write(MemoryRecord(
        type="semantic", content="An unrelated finding.", task_id="t2", source_agent="x",
        verification_state="verified", tags=["planning"], provenance="x",
    ))
    result = get_research(store)
    assert result.total == 1
    assert "research finding" in result.items[0].title


def test_research_service_includes_knowledge_provider_records() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(MemoryRecord(
        type="semantic", content="Verified from a knowledge provider.", task_id="t1",
        source_agent="knowledge:memory_knowledge", verification_state="verified",
        tags=[], provenance="knowledge:memory_knowledge",
    ))
    result = get_research(store)
    assert result.total == 1


def test_research_endpoint_responds_with_valid_shape_even_when_empty() -> None:
    response = client.get("/api/research")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert body["total"] == len(body["items"])


# ---------------------------------------------------------------------------
# /api/dashboard — real aggregates
# ---------------------------------------------------------------------------


def test_dashboard_service_aggregates_are_real() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(MemoryRecord(
        type="episodic", content="Task ran. Final status: completed.", task_id="t1",
        source_agent="aion", verification_state="unverified", tags=[], provenance="workflow_runner",
    ))
    result = get_dashboard(store)
    assert result.saved_memories == 1
    assert result.active_agents == 4
    assert len(result.agent_activity) == 4


def test_dashboard_endpoint_end_to_end() -> None:
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["active_agents"] == 4
    assert body["total_tasks"] >= 0


# ---------------------------------------------------------------------------
# /api/chat contract fully unchanged
# ---------------------------------------------------------------------------


def test_chat_contract_still_unchanged_after_route_rewiring() -> None:
    response = client.post("/api/chat", json={"message": "Summarize the plan"})
    assert response.status_code == 200
    body = response.json()
    for field in ("task_id", "conversation_id", "answer", "mode", "status", "used_agents", "confidence"):
        assert field in body


# ---------------------------------------------------------------------------
# /api/workflows — honestly still demo data
# ---------------------------------------------------------------------------


def test_workflows_endpoint_still_responds_and_is_documented_as_demo() -> None:
    """No backend Workflow entity exists — confirmed still responding
    correctly with its pre-existing static contract, not silently broken."""
    response = client.get("/api/workflows")
    assert response.status_code == 200
    assert "items" in response.json()
