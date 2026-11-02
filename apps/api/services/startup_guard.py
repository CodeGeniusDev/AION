"""Startup safety guard (Phase B hardening).

Localhost development runs unauthenticated by design (``AION_REQUIRE_AUTH``
is opt-in). That is only safe while nothing else can reach the machine. The
combination this guard watches for is genuinely dangerous: auth OFF **and**
the desktop bridge answering — any network peer could then create approvals
and the bridge would execute real desktop tools.

The guard NEVER changes behavior: it logs exactly one WARNING (or INFO when
the bridge is dark) and prints no secret values. Called at app startup; the
bridge probe reuses the desktop client's unauthenticated ``/health`` route.
"""

from typing import Callable, Optional

import httpx

from config import settings
from observability.logging_config import get_logger
from services.desktop_bridge_client import BridgeError, DesktopBridgeClient

logger = get_logger("startup_guard")

_PROBE_TIMEOUT_SECONDS = 1.5


def _bridge_reachable() -> bool:
    """Best-effort probe of the configured bridge. Any transport error,
    timeout or HTTP error counts as unreachable — startup must never fail
    because of this check."""
    client = DesktopBridgeClient(
        base_url=settings.agent_bridge_url,
        timeout_seconds=_PROBE_TIMEOUT_SECONDS,
    )
    try:
        client.health()
    except (BridgeError, httpx.HTTPError):
        return False
    return True


def check_startup_safety(
    bridge_reachable: Callable[[], bool] = _bridge_reachable,
    require_auth: Optional[bool] = None,
) -> None:
    """Log the auth-posture warning. Params are injectable for tests;
    production uses the defaults."""
    auth_on = require_auth if require_auth is not None else settings.require_auth
    if auth_on:
        return  # Authenticated deployment — nothing to warn about.
    if bridge_reachable():
        logger.warning(
            "AION_REQUIRE_AUTH is OFF and the desktop bridge at %s is "
            "reachable: unauthenticated callers can create approvals that "
            "execute real desktop tools. Set AION_REQUIRE_AUTH=1 and a "
            "strong AION_AGENT_SECRET before exposing this service beyond "
            "localhost.",
            settings.agent_bridge_url,
        )
    else:
        logger.info(
            "AION_REQUIRE_AUTH is OFF (localhost development mode); "
            "desktop bridge not reachable — approval execution unavailable."
        )
