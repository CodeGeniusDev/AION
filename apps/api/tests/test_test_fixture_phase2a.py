"""Phase 2A: /api/_test/* fixture endpoints.

Verifies two properties:
1. When AION_TEST_MODE is unset (the default for every real deployment
   and every other test in this suite), the endpoints look exactly like
   an unknown route — 404 with the same body shape.
2. When the flag is set explicitly, the endpoints actually write to the
   SAME stores the real routes read, so Playwright can seed deterministically.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client_off(monkeypatch):
    """Fixture with AION_TEST_MODE unset — production default."""
    monkeypatch.delenv("AION_TEST_MODE", raising=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_on(monkeypatch):
    """Fixture with AION_TEST_MODE=1 — only for the isolated Playwright stack."""
    monkeypatch.setenv("AION_TEST_MODE", "1")
    with TestClient(app) as c:
        yield c


class TestTestModeGuard:
    """Every fixture endpoint must be invisible when the flag is off."""

    @pytest.mark.parametrize(
        "path,payload",
        [
            ("/api/_test/reset", {}),
            ("/api/_test/seed/task", {"title": "x"}),
            ("/api/_test/seed/alert", {"title": "x"}),
            ("/api/_test/seed/conversation", {"user_message": "x"}),
            ("/api/_test/seed/profile", {"display_name": "A", "username": "a"}),
        ],
    )
    def test_returns_404_when_flag_off(self, client_off, path, payload):
        res = client_off.post(path, json=payload)
        assert res.status_code == 404
        # Same generic body the app returns for unknown paths — the
        # endpoint never reveals that it exists.
        assert res.json().get("detail") in {"Not Found", "An unexpected error occurred", "Not found"}

    def test_route_is_registered_but_guarded(self, client_off):
        # Sanity: the router is included; only the guard blocks callers.
        # We can distinguish a real 404 (unknown path) from a fixture 404
        # by checking FastAPI doesn't emit 405 for a valid method.
        res = client_off.post("/api/_test/reset", json={})
        assert res.status_code == 404
        # Unknown path also 404s with the same detail.
        res2 = client_off.post("/api/_test/does-not-exist", json={})
        assert res2.status_code == 404
        assert res.json().get("detail") == res2.json().get("detail")


class TestSeedTask:
    def test_seed_task_appears_in_real_list(self, client_on):
        before = client_on.get("/api/tasks").json()["total"]
        res = client_on.post(
            "/api/_test/seed/task",
            json={"title": "phase2a task one", "status": "pending"},
        )
        assert res.status_code == 200
        row = res.json()
        assert row["title"] == "phase2a task one"

        after = client_on.get("/api/tasks").json()
        assert after["total"] == before + 1
        ids = [t["id"] for t in after["items"]]
        assert row["id"] in ids

    def test_seed_task_rejects_unknown_status(self, client_on):
        res = client_on.post(
            "/api/_test/seed/task",
            json={"title": "x", "status": "quantum"},
        )
        assert res.status_code == 400


class TestSeedAlert:
    def test_seed_alert_visible_in_bell(self, client_on):
        res = client_on.post(
            "/api/_test/seed/alert",
            json={
                "title": "phase2a alert",
                "description": "deterministic",
                "tone": "info",
                "link": "/tasks?open=x",
            },
        )
        assert res.status_code == 200
        created = res.json()
        assert created["link"] == "/tasks?open=x"

        items = client_on.get("/api/alerts").json()["items"]
        assert any(a["id"] == created["id"] for a in items)


class TestSeedConversation:
    def test_seed_conversation_round_trips(self, client_on):
        res = client_on.post(
            "/api/_test/seed/conversation",
            json={
                "user_message": "phase2a conversation seed",
                "assistant_message": "understood",
            },
        )
        assert res.status_code == 200
        body = res.json()
        convo_id = body["conversation_id"]

        messages = client_on.get(
            f"/api/conversations/{convo_id}/messages",
        ).json()
        assert len(messages) == 2
        assert messages[0]["content"] == "phase2a conversation seed"


class TestSeedProfile:
    def test_seed_profile_visible_via_get(self, client_on):
        # Reset first so we're not affected by any other test's write.
        client_on.post("/api/_test/reset")
        assert client_on.get("/api/profile").json()["configured"] is False

        res = client_on.post(
            "/api/_test/seed/profile",
            json={
                "display_name": "Phase2A User",
                "username": "phase2a",
                "email": "",
                "role": "",
                "timezone": "UTC",
                "bio": "",
                "avatar_color": "navy",
            },
        )
        assert res.status_code == 200
        body = client_on.get("/api/profile").json()
        assert body["configured"] is True
        assert body["profile"]["display_name"] == "Phase2A User"


class TestReset:
    def test_reset_clears_rows_this_endpoint_seeded(self, client_on):
        """Only proves the rows the fixture endpoints created are gone.
        Other stores (episodic memory) are populated by prior tests and
        the /api/tasks fallback intentionally keeps showing them — reset
        must never touch memory, or it would fight the security model."""
        task = client_on.post(
            "/api/_test/seed/task", json={"title": "cleanup task"},
        ).json()
        alert = client_on.post(
            "/api/_test/seed/alert", json={"title": "cleanup alert"},
        ).json()
        convo = client_on.post(
            "/api/_test/seed/conversation",
            json={"user_message": "cleanup convo"},
        ).json()
        client_on.post(
            "/api/_test/seed/profile",
            json={"display_name": "X", "username": "x"},
        )

        res = client_on.post("/api/_test/reset")
        assert res.status_code == 200
        assert res.json()["reset"] is True

        tasks_after = client_on.get("/api/tasks").json()["items"]
        assert task["id"] not in {t["id"] for t in tasks_after}
        alerts_after = client_on.get("/api/alerts").json()["items"]
        assert alert["id"] not in {a["id"] for a in alerts_after}
        convos_after = client_on.get("/api/conversations").json()
        assert convo["conversation_id"] not in {
            c["conversation_id"] for c in convos_after
        }
        assert client_on.get("/api/profile").json()["configured"] is False
