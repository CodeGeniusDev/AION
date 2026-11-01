"""Local HTTP bridge for the AION Desktop Operating System MVP.

Exposes the local agent's tools over HTTP so the AION backend can call
them. The AION backend proxies calls like ``POST /api/execute_tool`` to
this bridge, which runs the actual desktop automation (Playwright,
PyAutoGUI, file operations, social APIs, voice).

Security
--------
* Bound to 127.0.0.1 only (localhost). Never bind to 0.0.0.0.
* Requires ``X-Aion-Secret`` header matching ``AION_AGENT_SECRET``
  (read from the environment only — there is no ``--secret`` CLI flag,
  to keep the secret out of shell history). Change this in production.
* ``/tools/execute`` additionally requires a one-time approval grant
  (``X-Aion-Approval`` header) previously registered via
  ``POST /approvals/grant``: the shared secret alone can no longer run a
  desktop tool. Grants are consumed atomically *before* the executor
  runs, so a replayed request executes nothing (403 ``already_consumed``).
  Grants live only in this process's memory — a bridge restart drops
  them and any in-flight execution fails safely.
* Both secret and grant comparisons are constant-time
  (``hmac.compare_digest``).
* Browser automation defaults to headless.

Endpoints
---------
  GET  /health                 — connectivity check
  POST /approvals/grant        — register a single-use execution grant (secret)
  POST /tools/execute          — execute a named local tool (secret + grant)

Request::

    {
      "tool": "browser_navigate",
      "parameters": {"url": "https://decoricks.com"},
      "task_id": "task-abc123",
      "approval_id": "appr-1a2b3c4d"
    }

Response::

    {
      "success": true,
      "result": {...},
      "task_id": "task-abc123",
      "duration_ms": 123.4
    }
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from aion_desktop.browser import BrowserManager
from aion_desktop.config import (
    get_allowed_dirs,
    get_log_level,
    get_workspace,
    load_config,
)
from aion_desktop.files import FileCopyTool, FileReadTool, FileWriteTool
from aion_desktop.voice import VoiceBridge, VoiceNotConfiguredError

logger = logging.getLogger("aion_desktop.bridge")


# ---------------------------------------------------------------------------
# One-time approval grants (Gate 2 of the human-in-the-loop system)
# ---------------------------------------------------------------------------

class _GrantStore:
    """In-process store of single-use execution grants registered by the
    AION backend after a human approval. Only SHA-256 token hashes are
    kept — a dump of this process can't be used to replay a grant.
    ``consume`` is the enforcement point: under a lock, it validates
    tool match + expiry and removes the entry *before* returning True,
    so exactly one request can ever hold a given grant."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._grants: dict[str, dict[str, str]] = {}  # approval_id -> grant
        self._consumed: set[str] = set()              # replay forensics only

    def add(self, *, approval_id: str, tool: str, token_hash: str, expires_at: str) -> None:
        with self._lock:
            self._grants[approval_id] = {
                "tool": tool, "token_hash": token_hash, "expires_at": expires_at,
            }

    def consume(self, approval_id: str, *, token: str, tool: str) -> tuple[bool, str]:
        """Returns (granted, reason). Never leaks whether a hash merely
        differs vs. was never issued beyond coarse categories."""
        presented = hashlib.sha256(token.encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            grant = self._grants.get(approval_id)
            if grant is None:
                return False, "already_consumed" if approval_id in self._consumed else "no_grant"
            if not hmac.compare_digest(grant["token_hash"], presented):
                return False, "invalid_token"
            if grant["tool"] != tool:
                return False, "tool_mismatch"
            if grant["expires_at"] <= now:
                del self._grants[approval_id]
                self._consumed.add(approval_id)
                return False, "expired"
            del self._grants[approval_id]      # pop-before-execute: atomic
            self._consumed.add(approval_id)
            return True, "granted"

    def prune_expired(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            stale = [k for k, g in self._grants.items() if g["expires_at"] <= now]
            for key in stale:
                del self._grants[key]
                self._consumed.add(key)
            return len(stale)



# ---------------------------------------------------------------------------
# Tool registry: tool name -> executor (sync wrapper for async tools)
# ---------------------------------------------------------------------------

def _executor_for(tool_name: str, workspace: Path, allowed_dirs: list[Path]):
    """Return a sync callable that executes the named tool and returns a
    plain dict (not a coroutine)."""
    if tool_name == "desktop_open_app":
        def _exec(params: dict[str, Any]) -> dict[str, Any]:
            import subprocess
            app = params.get("app", "")
            result = subprocess.run(
                ["osascript", "-e", f'tell application "{app}" to activate'],
                capture_output=True, text=True, timeout=15,
            )
            return {"success": result.returncode == 0,
                    "message": f"Opened '{app}'", "app": app}
        return _exec

    if tool_name == "desktop_list_apps":
        def _exec(params: dict[str, Any]) -> dict[str, Any]:
            import subprocess
            result = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to get name of processes'],
                capture_output=True, text=True, timeout=15,
            )
            # osascript returns the process names as ONE comma-separated line;
            # normalise newlines too so either layout parses correctly.
            stdout = result.stdout.replace("\n", ",")
            apps = [a.strip() for a in stdout.split(",") if a.strip()] \
                if result.returncode == 0 else []
            return {"success": True, "count": len(apps), "applications": apps}
        return _exec

    if tool_name == "desktop_screenshot":
        def _exec(params: dict[str, Any]) -> dict[str, Any]:
            import subprocess
            from datetime import datetime, timezone
            output_path = params.get("output_path")
            if not output_path:
                ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
                output_path = str(workspace / f"screenshot-{ts}.png")
            result = subprocess.run(
                ["screencapture", "-x", output_path],
                capture_output=True, text=True, timeout=20,
            )
            if result.returncode != 0:
                return {"success": False, "error": f"screencapture failed: {result.stderr}"}
            if not Path(output_path).exists():
                return {"success": False, "error": f"No screenshot created at {output_path}"}
            return {"success": True, "path": output_path,
                    "size": Path(output_path).stat().st_size}
        return _exec

    if tool_name == "browser_navigate":
        async def _exec(params: dict[str, Any]) -> dict[str, Any]:
            url = params.get("url", "")
            headless = params.get("headless", True)
            try:
                async with BrowserManager(headless=headless) as browser:
                    result = await browser.navigate(url)
                    return {"success": True, "result": result}
            except Exception as exc:
                return {"success": False, "error": str(exc)}
        return _exec

    if tool_name == "browser_screenshot":
        async def _exec(params: dict[str, Any]) -> dict[str, Any]:
            from datetime import datetime, timezone
            output_path = params.get("output_path")
            if not output_path:
                ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
                output_path = str(workspace / f"browser-screenshot-{ts}.png")
            try:
                async with BrowserManager(headless=True) as browser:
                    return await browser.screenshot(output_path)
            except Exception as exc:
                return {"success": False, "error": str(exc)}
        return _exec

    if tool_name == "file_read":
        async def _exec(params: dict[str, Any]) -> dict[str, Any]:
            tool = FileReadTool()
            result = await tool.execute(
                "task-local",
                {"path": params.get("path", ""),
                 "allowed_dirs": allowed_dirs},
            )
            return {"success": result.success, "message": result.content,
                    "error": result.error, "data": result.data}
        return _exec

    if tool_name == "file_write":
        async def _exec(params: dict[str, Any]) -> dict[str, Any]:
            tool = FileWriteTool()
            result = await tool.execute(
                "task-local",
                {"path": params.get("path", ""),
                 "content": params.get("content", ""),
                 "allowed_dirs": allowed_dirs},
            )
            return {"success": result.success, "message": result.content,
                    "error": result.error, "data": result.data}
        return _exec

    if tool_name == "file_copy":
        async def _exec(params: dict[str, Any]) -> dict[str, Any]:
            tool = FileCopyTool()
            result = await tool.execute(
                "task-local",
                {"src": params.get("src", ""),
                 "dest": params.get("dest", ""),
                 "allowed_dirs": allowed_dirs},
            )
            return {"success": result.success, "message": result.content,
                    "error": result.error, "data": result.data}
        return _exec

    if tool_name == "voice_listen":
        _bridge = VoiceBridge()

        def _exec(params: dict[str, Any]) -> dict[str, Any]:
            try:
                text = asyncio.run(_bridge.listen())
                return {"success": True, "text": text}
            except VoiceNotConfiguredError as exc:
                return {"success": False, "error": str(exc)}
        return _exec

    if tool_name == "voice_say":
        _bridge = VoiceBridge()

        def _exec(params: dict[str, Any]) -> dict[str, Any]:
            text = params.get("text", "")
            try:
                asyncio.run(_bridge.say(text))
                return {"success": True, "message": f"Spoke: {text[:60]}"}
            except VoiceNotConfiguredError as exc:
                return {"success": False, "error": str(exc)}
        return _exec

    return None  # unknown tool


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    log_level = get_log_level(config)
    configure_logging(log_level)
    workspace = get_workspace(config)
    logger.info("AION Bridge starting (port=%s, workspace=%s, headless=%s)",
                config["agent"]["port"], workspace, config["browser"]["headless"])
    yield
    logger.info("AION Bridge stopping")


def build_app(secret: str, port: int) -> FastAPI:
    # Security: the secret is the sole authentication for the bridge.
    # Refuse to create an app with an empty or placeholder secret.
    if not secret:
        raise ValueError(
            "Cannot create bridge app: AION_AGENT_SECRET is empty. "
            "Set AION_AGENT_SECRET in the environment before starting."
        )
    if secret == "change-me-in-production":
        raise ValueError(
            "Cannot create bridge app: AION_AGENT_SECRET is the placeholder "
            "\"change-me-in-production\". Set a real value before starting."
        )

    app = FastAPI(title="AION Desktop Agent Bridge", version="0.1.0", lifespan=lifespan)
    app.state.secret = secret
    app.state.port = port
    app.state.grants = _GrantStore()
    config = load_config()
    app.state.workspace = get_workspace(config)
    app.state.workspace_allowed = get_allowed_dirs(config)

    # Define routes inside build_app so `app` is in scope
    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Health check: no authentication required."""
        return {"status": "healthy", "service": "AION Desktop Agent Bridge"}

    def _require_secret(request: Request) -> None:
        """Constant-time shared-secret check (401 on failure)."""
        presented = request.headers.get("X-Aion-Secret", "")
        if not presented or not hmac.compare_digest(presented, app.state.secret):
            logger.warning("Unauthorized bridge request from %s", request.client)
            raise HTTPException(status_code=401, detail="Invalid or missing secret")

    @app.post("/approvals/grant")
    async def register_grant(request: Request) -> JSONResponse:
        """Register a single-use execution grant for a human-approved
        action. Called only by the authenticated AION backend (shared
        secret). Stores the SHA-256 token hash, never the raw token."""
        _require_secret(request)
        body = await request.json()
        approval_id = body.get("approval_id", "")
        tool = body.get("tool", "")
        token_hash = body.get("token_hash", "")
        expires_at = body.get("expires_at", "")
        if not approval_id or not tool or not token_hash or not expires_at:
            raise HTTPException(status_code=400, detail="Missing grant fields")
        # Defense in depth: reject anything that isn't a sha256 hex digest,
        # so a raw token can never be accidentally stored as a hash.
        if len(token_hash) != 64 or not all(c in "0123456789abcdef" for c in token_hash.lower()):
            raise HTTPException(status_code=400, detail="token_hash must be a SHA-256 hex digest")
        request.app.state.grants.add(
            approval_id=approval_id, tool=tool,
            token_hash=token_hash.lower(), expires_at=expires_at,
        )
        return JSONResponse(content={"granted": True, "approval_id": approval_id})

    @app.post("/tools/execute")
    async def execute_tool(request: Request) -> JSONResponse:
        # Gate 1: shared secret (constant-time).
        _require_secret(request)

        body = await request.json()
        tool_name = body.get("tool")
        if not tool_name:
            raise HTTPException(status_code=400, detail="Missing 'tool' name")

        # Gate 2: one-time human-approval grant. The secret alone is no
        # longer sufficient — every execution must present a valid,
        # unconsumed grant registered after an explicit approval.
        approval_token = request.headers.get("X-Aion-Approval", "")
        approval_id = body.get("approval_id", "")
        if not approval_token or not approval_id:
            logger.warning("Tool execute without approval grant from %s", request.client)
            raise HTTPException(status_code=403, detail="Missing X-Aion-Approval grant")
        granted, reason = request.app.state.grants.consume(
            approval_id, token=approval_token, tool=tool_name,
        )
        if not granted:
            logger.warning("Approval grant rejected (%s) for tool '%s'", reason, tool_name)
            raise HTTPException(status_code=403, detail=f"Invalid approval grant: {reason}")

        parameters = body.get("parameters", {})
        task_id = body.get("task_id", "unknown")
        workspace = app.state.workspace

        tool_func = _executor_for(tool_name, workspace, app.state.workspace_allowed)
        if tool_func is None:
            raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")

        started = time.monotonic()
        try:
            result: Any = tool_func(parameters)
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as exc:
            logger.exception("Tool '%s' raised: %s", tool_name, exc)
            result = {"success": False, "error": str(exc)}

        duration_ms = round((time.monotonic() - started) * 1000, 1)
        response = {
            "success": bool(result.get("success", False)),
            "result": result,
            "task_id": task_id,
            "duration_ms": duration_ms,
        }
        logger.info("Tool '%s' completed in %.1fms", tool_name, duration_ms)
        return JSONResponse(content=response)
    return app


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def configure_logging(level: int) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(port: int = 8080, headless: bool = True) -> None:
    import os
    import uvicorn
    import sys

    # Security: secret MUST come from env AION_AGENT_SECRET only.
    # No --secret CLI flag (prevents shell history leaks).
    secret = os.environ.get("AION_AGENT_SECRET", "")
    if not secret:
        logger.error(
            "Refusing to start: AION_AGENT_SECRET is not set. "
            "Set it in the environment (e.g. export AION_AGENT_SECRET='your-secure-secret') and re-run."
        )
        sys.exit(1)

    # Double-check it's not a placeholder value
    if secret == "change-me-in-production":
        logger.error(
            "Refusing to start: AION_AGENT_SECRET is set to the placeholder "
            "\"change-me-in-production\". Set a real value before starting."
        )
        sys.exit(1)

    configure_logging(logging.INFO)
    app = build_app(secret, port)
    logger.info("Starting AION bridge on 127.0.0.1:%d", port)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
