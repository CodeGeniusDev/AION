"""Request/correlation ID propagation via contextvars.

Per-request isolation, made explicit rather than accidental: every inbound
HTTP request gets a `request_id` (always generated fresh) and a
`correlation_id` (taken from an incoming `X-Correlation-ID` header if the
caller supplies one, so a request can be traced across service boundaries
in a future distributed deployment; otherwise equal to request_id). Both
are bound to contextvars by main.py's middleware and read by the logging
filter (observability/logging_config.py) and anywhere else that wants to
tag output with "which request produced this."

This does NOT implement multi-tenant data isolation — there is no user/
tenant concept in this codebase yet (see architecture audit). It makes the
existing task_id-based isolation (which was already correct, just
undocumented as a deliberate design) traceable end-to-end instead.
"""

from contextvars import ContextVar
from uuid import uuid4

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_id() -> str:
    return uuid4().hex[:16]


def bind_request_context(*, request_id: str | None = None, correlation_id: str | None = None) -> tuple[str, str]:
    """Bind request/correlation IDs for the current async context. Returns
    the (possibly freshly generated) values actually bound."""
    resolved_request_id = request_id or new_id()
    resolved_correlation_id = correlation_id or resolved_request_id
    _request_id.set(resolved_request_id)
    _correlation_id.set(resolved_correlation_id)
    return resolved_request_id, resolved_correlation_id


def get_request_id() -> str | None:
    return _request_id.get()


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def reset_request_context() -> None:
    """Test/administrative use: clear bound context. Not called during
    normal request handling — each request naturally gets a fresh context
    via ContextVar's per-task isolation in asyncio."""
    _request_id.set(None)
    _correlation_id.set(None)
