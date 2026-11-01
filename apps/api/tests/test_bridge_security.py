"""Security tests for desktop/aion_desktop/bridge.py.

Tests verify:
- Bridge refuses to start with empty or "change-me-in-production" secret
- Bridge binds only to 127.0.0.1
- POST /tools/execute returns 401 without X-Aion-Secret header
- GET /health is accessible without authentication

Run with: pytest -v test_bridge_security.py
"""

import os
import subprocess
import sys
from pathlib import Path

# Add desktop to path for imports
# test_bridge_security.py is at apps/api/tests/test_bridge_security.py
# -> apps/api/tests/ -> apps/api -> apps -> root -> desktop/
desktop_path = Path(__file__).resolve().parent.parent.parent.parent / "desktop"
sys.path.insert(0, str(desktop_path))
# Also add apps/api so aion_desktop can import from tools and models
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from aion_desktop.bridge import build_app, main  # noqa: E402


def _run_bridge_with_env(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    """Run main() with a custom environment, returning the CompletedProcess."""
    # Build env: copy current, override with test values
    env = dict(os.environ)
    env.pop("AION_AGENT_SECRET", None)  # start clean
    env.update(env_overrides)

    return subprocess.run(
        [sys.executable, "-c",
         "from aion_desktop.bridge import main; main(port=8081)"],
        capture_output=True, text=True, timeout=5,
        cwd=str(desktop_path),
        env=env,
    )


def test_bridge_refuses_empty_secret():
    """Bridge must refuse to start with empty secret."""
    result = _run_bridge_with_env({})  # AION_AGENT_SECRET not set
    assert result.returncode != 0, f"Expected non-zero exit, got {result.returncode}"
    assert "secret" in result.stderr.lower() or "refusing" in result.stderr.lower(), \
        f"Expected error about secret, got: {result.stderr}"


def test_bridge_refuses_default_secret():
    """Bridge must refuse to start with 'change-me-in-production' secret."""
    result = _run_bridge_with_env({"AION_AGENT_SECRET": "change-me-in-production"})
    assert result.returncode != 0, f"Expected non-zero exit, got {result.returncode}"
    assert "secret" in result.stderr.lower() or "refusing" in result.stderr.lower(), \
        f"Expected error about secret, got: {result.stderr}"


def test_bridge_refuses_empty_env_secret():
    """Bridge must refuse to start when AION_AGENT_SECRET is set to empty string."""
    result = _run_bridge_with_env({"AION_AGENT_SECRET": ""})
    assert result.returncode != 0, f"Expected non-zero exit, got {result.returncode}"
    assert "secret" in result.stderr.lower() or "refusing" in result.stderr.lower(), \
        f"Expected error about secret, got: {result.stderr}"


def test_bridge_binds_to_127_0_0_1():
    """Bridge must bind to 127.0.0.1 only, not 0.0.0.0."""
    import inspect
    src = inspect.getsource(main)
    assert "127.0.0.1" in src, "main() must call uvicorn with host='127.0.0.1'"
    assert 'host="0.0.0.0"' not in src, "main() must NOT bind to 0.0.0.0"


def test_health_open_without_auth():
    """GET /health must be accessible without authentication."""
    app = build_app("my-secure-secret", port=8083)
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_tools_execute_requires_secret():
    """POST /tools/execute must return 401 without X-Aion-Secret header."""
    app = build_app("my-secure-secret", port=8084)
    client = TestClient(app)

    # Request without header should fail
    response = client.post(
        "/tools/execute",
        json={"tool": "desktop_list_apps", "parameters": {}, "task_id": "test"},
    )
    assert response.status_code == 401

    # Request with wrong header should fail
    response = client.post(
        "/tools/execute",
        json={"tool": "desktop_list_apps", "parameters": {}, "task_id": "test"},
        headers={"X-Aion-Secret": "wrong-secret"},
    )
    assert response.status_code == 401

    # Correct secret but NO approval grant: the shared secret alone is no
    # longer sufficient — the request is refused with 403 (Gate 2), never
    # reaching the tool executor.
    response = client.post(
        "/tools/execute",
        json={"tool": "desktop_list_apps", "parameters": {}, "task_id": "test",
              "approval_id": "appr-none"},
        headers={"X-Aion-Secret": "my-secure-secret"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# One-time approval grants (Gate 2)
# ---------------------------------------------------------------------------

import hashlib  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402


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


def test_grant_endpoint_requires_secret():
    """POST /approvals/grant must be 401 without the shared secret."""
    app = build_app("my-secure-secret", port=8090)
    client = TestClient(app)
    response = _grant(client, "wrong", approval_id="appr-1", tool="file_read", token="t")
    assert response.status_code == 401


def test_grant_endpoint_rejects_raw_token_as_hash():
    """A non-SHA256-hex token_hash (e.g. a raw token passed by mistake) is
    rejected 400, so a usable grant secret can never be stored verbatim."""
    app = build_app("my-secure-secret", port=8091)
    client = TestClient(app)
    response = _grant(client, "my-secure-secret", approval_id="appr-1",
                      tool="file_read", token="not-a-hash")
    # token arg is hashed by _grant, so pass a bogus hash directly instead:
    response = client.post(
        "/approvals/grant",
        json={"approval_id": "appr-1", "tool": "file_read",
              "token_hash": "raw-token-not-64-hex", "expires_at": _future()},
        headers={"X-Aion-Secret": "my-secure-secret"},
    )
    assert response.status_code == 400


def test_missing_grant_is_rejected():
    """Execute with a valid secret but no X-Aion-Approval grant → 403."""
    app = build_app("my-secure-secret", port=8092)
    client = TestClient(app)
    response = client.post(
        "/tools/execute",
        json={"tool": "file_read", "parameters": {"path": "x"}, "task_id": "t",
              "approval_id": "appr-missing"},
        headers={"X-Aion-Secret": "my-secure-secret"},
    )
    assert response.status_code == 403


def test_grant_and_secret_execute_mocked_tool_once(monkeypatch):
    """The happy path: a valid, unconsumed grant + the secret runs the
    executor exactly once, and a replayed identical request is refused."""
    import aion_desktop.bridge as bridge_module

    calls = {"n": 0}

    def fake_executor_for(tool_name, workspace, allowed_dirs):
        def _exec(params):
            calls["n"] += 1
            return {"success": True, "tool": tool_name}
        return _exec

    monkeypatch.setattr(bridge_module, "_executor_for", fake_executor_for)
    app = build_app("my-secure-secret", port=8093)
    client = TestClient(app)
    token = "grant-token-live"
    assert _grant(client, "my-secure-secret", approval_id="appr-live",
                  tool="file_read", token=token).status_code == 200

    headers = {"X-Aion-Secret": "my-secure-secret", "X-Aion-Approval": token}
    body = {"tool": "file_read", "parameters": {"path": "x"}, "task_id": "t",
            "approval_id": "appr-live"}
    ok = client.post("/tools/execute", json=body, headers=headers)
    assert ok.status_code == 200 and ok.json()["success"] is True
    assert calls["n"] == 1

    # Replay of the exact same consumed grant must not run again.
    replay = client.post("/tools/execute", json=body, headers=headers)
    assert replay.status_code == 403
    assert "already_consumed" in replay.json()["detail"]
    assert calls["n"] == 1  # never re-executed


def test_grant_tool_mismatch_rejected(monkeypatch):
    """A grant issued for one tool cannot execute a different tool."""
    import aion_desktop.bridge as bridge_module
    monkeypatch.setattr(
        bridge_module, "_executor_for",
        lambda *a, **k: (lambda params: {"success": True}),
    )
    app = build_app("my-secure-secret", port=8094)
    client = TestClient(app)
    token = "grant-wrong-tool"
    _grant(client, "my-secure-secret", approval_id="appr-mm", tool="file_read", token=token)
    response = client.post(
        "/tools/execute",
        json={"tool": "file_write", "parameters": {}, "task_id": "t", "approval_id": "appr-mm"},
        headers={"X-Aion-Secret": "my-secure-secret", "X-Aion-Approval": token},
    )
    assert response.status_code == 403
    assert "tool_mismatch" in response.json()["detail"]


def test_expired_grant_rejected():
    """A grant past its expiry is refused and pruned."""
    app = build_app("my-secure-secret", port=8095)
    client = TestClient(app)
    token = "grant-expired"
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    _grant(client, "my-secure-secret", approval_id="appr-exp", tool="file_read",
           token=token, expires_at=past)
    response = client.post(
        "/tools/execute",
        json={"tool": "file_read", "parameters": {"path": "x"}, "task_id": "t",
              "approval_id": "appr-exp"},
        headers={"X-Aion-Secret": "my-secure-secret", "X-Aion-Approval": token},
    )
    assert response.status_code == 403
    assert "expired" in response.json()["detail"]
