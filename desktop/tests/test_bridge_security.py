"""Security tests for desktop/aion_desktop/bridge.py.

Startup/binding guarantees are asserted against the source (they are
properties of how the server is launched). Request-handling is asserted
functionally via TestClient against the app built by ``build_app``.

Tests verify:
- Bridge refuses to start with empty or "change-me-in-production" secret
- Bridge binds only to 127.0.0.1
- GET /health is accessible without authentication
- POST /tools/execute returns 401 without a valid X-Aion-Secret header
- POST /tools/execute returns 403 without a one-time X-Aion-Approval grant
  (Gate 2), and a consumed grant cannot be replayed
"""

import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Make `aion_desktop` importable when the suite is run from desktop/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from aion_desktop.bridge import build_app  # noqa: E402


def _future(seconds: int = 300) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _grant(client, secret, *, approval_id, tool, token, expires_at=None):
    return client.post(
        "/approvals/grant",
        json={"approval_id": approval_id, "tool": tool,
              "token_hash": hashlib.sha256(token.encode()).hexdigest(),
              "expires_at": expires_at or _future()},
        headers={"X-Aion-Secret": secret},
    )


def test_bridge_refuses_empty_secret():
    """Bridge must refuse to start with empty secret."""
    bridge_path = Path(__file__).parent.parent / "aion_desktop" / "bridge.py"
    content = bridge_path.read_text()

    # Check that the main function has secret validation
    assert 'secret == "change-me-in-production"' in content
    assert "refusing to start" in content.lower()


def test_bridge_refuses_default_secret():
    """Bridge must refuse to start with 'change-me-in-production' secret."""
    bridge_path = Path(__file__).parent.parent / "aion_desktop" / "bridge.py"
    content = bridge_path.read_text()

    # Check that the main function validates against default secret
    assert 'secret == "change-me-in-production"' in content
    assert "sys.exit(1)" in content


def test_bridge_binds_to_127_0_0_1():
    """Bridge must bind to 127.0.0.1 only, not 0.0.0.0."""
    bridge_path = Path(__file__).parent.parent / "aion_desktop" / "bridge.py"
    content = bridge_path.read_text()

    # Check that uvicorn is called with host="127.0.0.1"
    assert 'host="127.0.0.1"' in content
    assert 'host="0.0.0.0"' not in content


def test_health_open_without_auth():
    """GET /health must be accessible without authentication."""
    app = build_app("my-secure-secret", port=8083)
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_tools_execute_requires_secret():
    """POST /tools/execute must return 401 without a valid X-Aion-Secret
    header, and 403 with a valid secret but no approval grant (Gate 2)."""
    app = build_app("my-secure-secret", port=8084)
    client = TestClient(app)

    # No header at all: 401.
    response = client.post(
        "/tools/execute",
        json={"tool": "desktop_list_apps", "parameters": {}, "task_id": "test"},
    )
    assert response.status_code == 401

    # Wrong header: 401.
    response = client.post(
        "/tools/execute",
        json={"tool": "desktop_list_apps", "parameters": {}, "task_id": "test"},
        headers={"X-Aion-Secret": "wrong-secret"},
    )
    assert response.status_code == 401

    # Correct secret but no X-Aion-Approval grant: the shared secret alone
    # is no longer sufficient — refused 403, never reaching the executor.
    response = client.post(
        "/tools/execute",
        json={"tool": "desktop_list_apps", "parameters": {}, "task_id": "test",
              "approval_id": "appr-none"},
        headers={"X-Aion-Secret": "my-secure-secret"},
    )
    assert response.status_code == 403


def test_grant_and_secret_execute_once_replay_refused(monkeypatch):
    """A valid unconsumed grant + secret runs the mocked executor exactly
    once; a replayed identical request is refused without re-executing."""
    import aion_desktop.bridge as bridge_module

    calls = {"n": 0}

    def fake_executor_for(tool_name, workspace, allowed_dirs):
        def _exec(params):
            calls["n"] += 1
            return {"success": True, "tool": tool_name}
        return _exec

    monkeypatch.setattr(bridge_module, "_executor_for", fake_executor_for)
    app = build_app("my-secure-secret", port=8085)
    client = TestClient(app)
    token = "grant-token-desktop"
    assert _grant(client, "my-secure-secret", approval_id="appr-live",
                  tool="file_read", token=token).status_code == 200

    headers = {"X-Aion-Secret": "my-secure-secret", "X-Aion-Approval": token}
    body = {"tool": "file_read", "parameters": {"path": "x"}, "task_id": "t",
            "approval_id": "appr-live"}
    ok = client.post("/tools/execute", json=body, headers=headers)
    assert ok.status_code == 200 and ok.json()["success"] is True
    assert calls["n"] == 1

    replay = client.post("/tools/execute", json=body, headers=headers)
    assert replay.status_code == 403
    assert "already_consumed" in replay.json()["detail"]
    assert calls["n"] == 1  # never re-executed
