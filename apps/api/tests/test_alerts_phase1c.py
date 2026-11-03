"""Phase 1C: additive alert fields (`created_at`, `link`).

Backward compatibility rules:
- GET /api/alerts keeps every pre-existing field untouched.
- Task alerts deep-link to /tasks?open=<task_id>; approval alerts to
  /desktop?approval=<id> (set where each alert is created).
- Databases created before the `link` column are migrated on open.
"""

import sqlite3

from fastapi.testclient import TestClient

from main import app
from memory.alert_store import AlertStore


def test_created_at_and_link_exposed_by_endpoint():
    client = TestClient(app)
    res = client.get("/api/alerts")
    assert res.status_code == 200
    for item in res.json()["items"]:
        # Legacy fields still present (contract unchanged).
        assert {"id", "title", "description", "time", "category", "unread", "tone"} <= set(item)
        assert "created_at" in item and "link" in item


def test_store_create_persists_link_and_created_at(tmp_path):
    store = AlertStore(db_path=str(tmp_path / "alerts.db"))
    created = store.create(
        title="Deploy finished", description="v2 is live",
        category="system", link="/settings",
    )
    assert created["link"] == "/settings"
    assert created["created_at"].endswith("+00:00")

    listed = store.list_all()
    assert listed[0]["link"] == "/settings"
    assert listed[0]["created_at"] == created["created_at"]


def test_create_without_link_stays_null(tmp_path):
    store = AlertStore(db_path=str(tmp_path / "alerts.db"))
    store.create(title="Plain", description="No link here")
    assert store.list_all()[0]["link"] is None


def test_task_alert_deep_links_to_task(tmp_path):
    store = AlertStore(db_path=str(tmp_path / "alerts.db"))
    alert = store.create_task_alert(
        task_id="task-42", message_preview="Summarize Q3", status="completed",
    )
    assert alert["link"] == "/tasks?open=task-42"


def test_legacy_schema_is_migrated_on_open(tmp_path):
    """A pre-`link` database must open cleanly and report link=None."""
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE alerts (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            time TEXT NOT NULL,
            category TEXT NOT NULL,
            unread INTEGER NOT NULL DEFAULT 1,
            tone TEXT NOT NULL DEFAULT 'info',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO alerts VALUES ('a1', 'Old alert', 'body', 'Jan 01', "
        "'system', 1, 'info', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    store = AlertStore(db_path=path)
    row = store.list_all()[0]
    assert row["link"] is None
    assert row["created_at"] == "2026-01-01T00:00:00+00:00"
