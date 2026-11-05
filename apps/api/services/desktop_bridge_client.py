"""HTTP client for the local desktop agent bridge (127.0.0.1:8080).

This is the only component that holds ``AION_AGENT_SECRET`` — the secret
travels on server-to-server requests to the bridge and is never exposed
to the frontend. Every protected execution additionally carries a
one-time grant token obtained via :meth:`register_grant`: the bridge
consumes the grant atomically before executing, so a replayed or
duplicated request can never run the same action twice even if this
client (or its secrets) were compromised.
"""

import hashlib
import secrets
from typing import Any

import httpx

from config import settings


class BridgeError(RuntimeError):
    """The bridge rejected or failed the request. Carries an HTTP status
    when one was received (so callers can distinguish 4xx policy failures
    from transport errors), None otherwise."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DesktopBridgeClient:
    def __init__(
        self,
        base_url: str | None = None,
        secret: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (base_url if base_url is not None else settings.agent_bridge_url).rstrip("/")
        self.secret = secret if secret is not None else settings.agent_secret
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.bridge_timeout_seconds

    def _headers(self, approval_token: str | None = None) -> dict[str, str]:
        headers = {"X-Aion-Secret": self.secret}
        if approval_token is not None:
            headers["X-Aion-Approval"] = approval_token
        return headers

    def _post(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}{path}", json=payload, headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise BridgeError(f"bridge unreachable: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text[:200])
            except Exception:
                detail = response.text[:200]
            raise BridgeError(f"bridge returned {response.status_code}: {detail}",
                              status_code=response.status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise BridgeError("bridge returned a non-JSON response") from exc

    def health(self) -> dict[str, Any]:
        """Connectivity probe. The bridge /health route needs no
        authentication, so this call deliberately carries NO secret —
        a health check must never put the credential on the wire."""
        try:
            response = httpx.get(
                f"{self.base_url}/health",
                timeout=min(self.timeout_seconds, 3.0),
            )
        except httpx.HTTPError as exc:
            raise BridgeError(f"bridge unreachable: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise BridgeError(
                f"bridge returned {response.status_code}",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise BridgeError("bridge returned a non-JSON response") from exc

    def register_grant(
        self, *, approval_id: str, tool: str, token: str, expires_at: str,
    ) -> None:
        """Whitelist a single-use execution grant on the bridge. The
        bridge stores only SHA-256(token); the raw token is held in memory
        by the caller just long enough to make the one execute call."""
        self._post("/approvals/grant", {
            "approval_id": approval_id,
            "tool": tool,
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "expires_at": expires_at,
        }, self._headers())

    def execute(
        self, *, tool: str, parameters: dict[str, Any], task_id: str,
        approval_id: str, token: str,
    ) -> dict[str, Any]:
        """Execute a tool on the bridge under a one-time grant. Raises
        BridgeError on any transport or HTTP failure — the caller must
        treat that as 'did not execute or outcome unknown' and mark the
        approval failed, never retry with the same grant."""
        return self._post("/tools/execute", {
            "tool": tool,
            "parameters": parameters,
            "task_id": task_id,
            "approval_id": approval_id,
        }, self._headers(approval_token=token))


def new_grant_token() -> str:
    """High-entropy single-use grant token (256 bits, hex)."""
    return secrets.token_hex(32)
