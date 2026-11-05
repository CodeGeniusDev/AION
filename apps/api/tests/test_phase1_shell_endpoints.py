"""Phase 1 shell endpoints verification:
Tests all backend endpoints supporting the Phase 1 application shell:
- System health and identity
- Settings & Profile updates
- Notifications & Alerts
- Real data endpoints powering universal search
"""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint_contract(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["service"] == "AION API"
    assert "version" in data
    assert "model_name" in data
    assert "memory" in data
    assert "agents" in data


def test_settings_get_and_put(client):
    # GET settings
    get_res = client.get("/api/settings")
    assert get_res.status_code == 200
    original = get_res.json()
    assert "workspace_name" in original
    assert "theme" in original
    assert "default_view" in original

    # PUT settings with dark theme and new workspace name
    update_payload = {
        **original,
        "workspace_name": "Antigravity Engineering",
        "theme": "dark",
        "default_view": "chat",
        "notify_task_completions": True,
        "notify_system_health": False,
        "notify_weekly_summary": True,
    }
    put_res = client.put("/api/settings", json=update_payload)
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["workspace_name"] == "Antigravity Engineering"
    assert updated["theme"] == "dark"
    assert updated["default_view"] == "chat"
    assert updated["notify_system_health"] is False
    assert updated["notify_weekly_summary"] is True

    # Confirm persistence in subsequent GET
    get_res2 = client.get("/api/settings")
    assert get_res2.status_code == 200
    assert get_res2.json()["workspace_name"] == "Antigravity Engineering"
    assert get_res2.json()["theme"] == "dark"

    # Reset back to default
    client.put("/api/settings", json=original)


def test_alerts_lifecycle(client):
    # GET alerts
    res = client.get("/api/alerts")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "unread_count" in data
    assert "total" in data

    # Mark all read
    mark_all = client.post("/api/alerts/mark-all-read")
    assert mark_all.status_code == 200
    assert "updated" in mark_all.json()

    # Verify unread count is now 0
    res_after = client.get("/api/alerts")
    assert res_after.status_code == 200
    assert res_after.json()["unread_count"] == 0


def test_universal_search_data_sources(client):
    """Verify that all backend endpoints called by universal global search respond correctly."""
    # Tasks
    tasks_res = client.get("/api/tasks")
    assert tasks_res.status_code == 200
    assert "items" in tasks_res.json()

    # Agents
    agents_res = client.get("/api/agents")
    assert agents_res.status_code == 200
    assert "items" in agents_res.json()

    # Memory search
    mem_res = client.get("/api/memories/records/search?q=test&limit=5")
    assert mem_res.status_code == 200
    assert "items" in mem_res.json()

    # Conversations
    conv_res = client.get("/api/conversations")
    assert conv_res.status_code == 200
    assert isinstance(conv_res.json(), list)

    # Workflows
    wf_res = client.get("/api/workflows")
    assert wf_res.status_code == 200
    assert "items" in wf_res.json()
