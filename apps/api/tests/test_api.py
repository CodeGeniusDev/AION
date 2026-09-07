from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "AION API is running"}


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("healthy", "degraded", "unhealthy")
    assert body["service"] == "AION API"
    assert "version" in body
    assert "model_name" in body
    assert body["gemini"]["status"] in ("ok", "degraded", "error")
    assert body["memory"]["status"] in ("ok", "degraded", "error")
    assert body["agents"]["status"] in ("ok", "degraded", "error")


def test_dashboard_reflects_real_backend_state() -> None:
    """Dashboard now sources real data from the live Agent Registry and
    Cognitive Memory store (see services/dashboard_service.py), not static
    demo numbers — total_tasks/saved_memories vary with actual runtime
    state (other tests in this session write real memory records), so this
    asserts real, deterministic invariants rather than fixed magic numbers."""
    response = client.get("/api/dashboard")
    body = response.json()
    assert response.status_code == 200
    assert body["active_agents"] == 4  # the four real registered agents are always available in tests
    assert body["total_tasks"] >= 0
    assert body["saved_memories"] >= 0
    assert body["system_health"] >= 0  # real score computed from Gemini/Memory/Agents checks
    assert len(body["agent_activity"]) == 4
    assert isinstance(body["recent_tasks"], list)


def test_chat_returns_aion_response() -> None:
    response = client.post("/api/chat", json={"message": "Hello AION", "mode": "auto"})
    assert response.status_code == 200
    body = response.json()
    assert body["author"] == "AION"
    assert body["mode"] == "auto"
    assert body["status"] == "completed"
    assert body["used_agents"] == []
    assert body["development_mode"] is True


def test_chat_rejects_empty_messages() -> None:
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_rejects_invalid_mode() -> None:
    response = client.post("/api/chat", json={"message": "Hello", "mode": "invalid"})
    assert response.status_code == 422


def test_manual_chat_requires_agents() -> None:
    response = client.post("/api/chat", json={"message": "Plan this", "mode": "manual", "selected_agents": []})
    assert response.status_code == 422


def test_agents_returns_four_specialists() -> None:
    response = client.get("/api/agents")
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 4
    assert len(body["items"]) == 4
    assert {agent["id"] for agent in body["items"]} == {"planner", "researcher", "critic", "memory"}


def test_tasks_returns_demo_tasks() -> None:
    response = client.get("/api/tasks")
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == len(body["items"])
    assert body["total"] > 0
    assert all("id" in task and "status" in task for task in body["items"])


def test_task_returns_single_task_by_id() -> None:
    """Tasks are now derived from real episodic Cognitive Memory records
    (see services/tasks_service.py), so there is no fixed "task-001" id —
    fetch a real one from the live list first, matching the new contract."""
    client.post("/api/chat", json={"message": "Create a roadmap and steps for launch"})
    list_response = client.get("/api/tasks")
    real_task_id = list_response.json()["items"][0]["id"]

    response = client.get(f"/api/tasks/{real_task_id}")
    body = response.json()
    assert response.status_code == 200
    assert body["id"] == real_task_id
    assert body["title"]


def test_task_returns_404_for_missing_task() -> None:
    response = client.get("/api/tasks/does-not-exist")
    assert response.status_code == 404


def test_memory_returns_categories_and_policies() -> None:
    response = client.get("/api/memory")
    body = response.json()
    assert response.status_code == 200
    assert len(body["categories"]) == 3
    assert len(body["policies"]) > 0


def test_workflows_returns_demo_workflows() -> None:
    response = client.get("/api/workflows")
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == len(body["items"])
    assert all("agents" in workflow for workflow in body["items"])


def test_research_returns_demo_notes() -> None:
    response = client.get("/api/research")
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == len(body["items"])
    assert all("type" in note for note in body["items"])

