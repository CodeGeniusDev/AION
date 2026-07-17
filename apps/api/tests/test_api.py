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
    assert response.json() == {"status": "healthy", "service": "AION API"}


def test_dashboard_contains_required_demo_data() -> None:
    response = client.get("/api/dashboard")
    body = response.json()
    assert response.status_code == 200
    assert body["total_tasks"] == 128
    assert body["active_agents"] == 4
    assert body["saved_memories"] == 24
    assert body["system_health"] == 98
    assert len(body["recent_tasks"]) > 0
    assert len(body["agent_activity"]) == 4


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

