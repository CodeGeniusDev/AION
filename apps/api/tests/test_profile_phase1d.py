"""Phase 1D: profile endpoints + settings persistence in the profile store.

The autouse conftest fixture points AION_PROFILE_DB_PATH at a throwaway
database and clears tables between tests — the real local file is never
touched and no test ever sees a seeded profile.
"""

import pytest
from fastapi.testclient import TestClient

from main import app
from memory.profile_store import (
    ProfileStore,
    get_default_profile_store,
    reset_default_profile_store,
)


@pytest.fixture
def client():
    return TestClient(app)


VALID = {
    "display_name": "Amina Yusuf",
    "username": "",
    "email": "amina@example.com",
    "role": "Operations lead",
    "timezone": "Asia/Dubai",
    "bio": "Runs the local AION workspace.",
    "avatar_color": "teal",
}


def test_first_run_reports_not_configured(client):
    res = client.get("/api/profile")
    assert res.status_code == 200
    body = res.json()
    assert body["configured"] is False
    assert body["profile"] is None


def test_put_then_get_roundtrip(client):
    put = client.put("/api/profile", json=VALID)
    assert put.status_code == 200
    body = put.json()
    assert body["configured"] is True
    assert body["profile"]["display_name"] == "Amina Yusuf"
    # Empty username is derived as a canonical slug.
    assert body["profile"]["username"] == "amina-yusuf"

    get = client.get("/api/profile").json()
    assert get["profile"]["email"] == "amina@example.com"
    assert get["profile"]["timezone"] == "Asia/Dubai"
    assert get["profile"]["avatar_color"] == "teal"


def test_created_at_survives_update(client):
    first = client.put("/api/profile", json=VALID).json()
    second = client.put(
        "/api/profile", json={**VALID, "display_name": "Amina Y."}
    ).json()
    assert second["created_at"] == first["created_at"]
    assert second["updated_at"] >= first["created_at"]


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("display_name", ""),
        ("display_name", "x" * 61),
        ("display_name", "   "),
        ("email", "not-an-email"),
        ("timezone", "Mars/Olympus"),
        ("bio", "b" * 201),
        ("avatar_color", "neon-pink"),
        ("username", "Has Spaces"),
    ],
)
def test_validation_returns_422(client, field, bad_value):
    res = client.put("/api/profile", json={**VALID, field: bad_value})
    assert res.status_code == 422


def test_optional_email_and_blank_role_are_allowed(client):
    res = client.put(
        "/api/profile", json={**VALID, "email": "", "role": "", "bio": ""}
    )
    assert res.status_code == 200
    assert res.json()["profile"]["email"] == ""


def test_explicit_username_is_respected(client):
    res = client.put("/api/profile", json={**VALID, "username": "ghost-runner"})
    assert res.json()["profile"]["username"] == "ghost-runner"


def test_settings_persist_in_the_same_store(client):
    original = client.get("/api/settings").json()
    updated = client.put(
        "/api/settings", json={**original, "workspace_name": "Yusuf Ops", "theme": "dark"}
    ).json()
    assert updated["workspace_name"] == "Yusuf Ops"

    # Simulate a restart: drop the cached store, reopen the same file.
    path = get_default_profile_store().db_path
    reset_default_profile_store()
    reopened = ProfileStore(path)
    assert reopened is not None
    body = client.get("/api/settings").json()
    assert body["workspace_name"] == "Yusuf Ops"
    assert body["theme"] == "dark"


def test_legacy_dim_theme_persists_as_dark(client):
    original = client.get("/api/settings").json()
    res = client.put(
        "/api/settings", json={**original, "theme": "dim"}
    )
    assert res.status_code == 200
    assert res.json()["theme"] == "dark"
    assert client.get("/api/settings").json()["theme"] == "dark"
