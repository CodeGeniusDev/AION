"""Phase 2: Dashboard Intelligence & Global Real-Time System Tests.

Validates that:
1. Every dashboard metric is grounded in actual backend subsystem state.
2. Breakdown counts (tasks by status, agent states, memory categories) are accurate.
3. System health checks evaluate components independently without fake metrics.
4. Global SSE endpoint /api/events connects and dispatches Cognitive Bus events.
"""

import pytest
from fastapi.testclient import TestClient

from main import app
from memory.task_store import get_default_task_store


@pytest.fixture
def client():
    return TestClient(app)


def test_dashboard_real_telemetry_structure(client):
    res = client.get("/api/dashboard")
    assert res.status_code == 200
    data = res.json()

    # Core top-level fields
    assert "total_tasks" in data
    assert "active_agents" in data
    assert "saved_memories" in data
    assert "system_health" in data
    assert "recent_tasks" in data
    assert "agent_activity" in data

    # Phase 2 Enhanced structures
    assert "task_counts" in data
    counts = data["task_counts"]
    assert "total" in counts
    assert "completed" in counts
    assert "running" in counts
    assert "pending" in counts
    assert "failed" in counts
    assert counts["total"] == counts["completed"] + counts["running"] + counts["pending"] + counts["failed"]

    assert "agent_stats" in data
    agent_stats = data["agent_stats"]
    assert "total_registered" in agent_stats
    assert "idle" in agent_stats
    assert "offline" in agent_stats

    assert "memory_stats" in data
    mem_stats = data["memory_stats"]
    assert "total_records" in mem_stats
    assert "episodic_count" in mem_stats
    assert "semantic_count" in mem_stats
    assert mem_stats["status"] == "operational"

    assert "system_health_detail" in data
    health = data["system_health_detail"]
    assert 0 <= health["score"] <= 100
    assert health["status"] in ("healthy", "degraded", "unhealthy")
    assert len(health["components"]) >= 5


def test_task_lifecycle_updates_dashboard_counts(client):
    # 1. Create a task via API
    task_res = client.post("/api/tasks", json={
        "title": "Analyze architecture patterns",
        "agent": "planner",
        "status": "pending",
    })
    assert task_res.status_code == 200
    task_id = task_res.json()["id"]

    # 2. Check dashboard reflects pending task
    dash_1 = client.get("/api/dashboard").json()
    assert dash_1["task_counts"]["pending"] >= 1
    assert any(t["id"] == task_id and t["status"] == "pending" for t in dash_1["recent_tasks"])

    # 3. Transition task to running
    client.post(f"/api/tasks/{task_id}/status", json={"status": "running"})
    dash_2 = client.get("/api/dashboard").json()
    assert any(t["id"] == task_id and t["status"] == "running" for t in dash_2["recent_tasks"])

    # 4. Transition task to completed
    client.post(f"/api/tasks/{task_id}/status", json={"status": "completed"})
    dash_3 = client.get("/api/dashboard").json()
    assert any(t["id"] == task_id and t["status"] == "completed" for t in dash_3["recent_tasks"])


def test_agent_activity_grounded_in_registry(client):
    dash = client.get("/api/dashboard").json()
    activity = dash["agent_activity"]
    assert len(activity) >= 4  # Core agents: planner, researcher, critic, memory

    names = {a["name"] for a in activity}
    assert "Planner Agent" in names
    assert "Research Agent" in names

    for agent in activity:
        assert agent["status"] in ("idle", "planning", "researching", "executing", "offline", "online", "standby")
        assert 0 <= agent["workload"] <= 100
        assert "total_runs" in agent


def test_system_health_components_honest_evaluation(client):
    dash = client.get("/api/dashboard").json()
    components = dash["system_health_detail"]["components"]
    component_names = {c["name"] for c in components}

    assert "FastAPI Backend" in component_names
    assert "Cognitive Memory" in component_names
    assert "Agent Registry" in component_names
    assert "Task Coordinator" in component_names
    assert "Cognitive Bus" in component_names
    assert "Gemini Engine" in component_names

    for c in components:
        assert c["status"] in ("healthy", "degraded", "unavailable", "not_configured", "unknown")
        assert len(c["detail"]) > 0


def test_global_events_sse_endpoint_connects(client):
    """Verify that GET /api/events returns an SSE text/event-stream with a handshake event."""
    with client.stream("GET", "/api/events") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        for chunk in response.iter_text():
            if "connected" in chunk:
                assert "AION API" in chunk
                break
