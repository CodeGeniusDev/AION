"""FastAPI authentication/authorization dependency.

Enforcement is gated by `settings.require_auth` (default False), so every
pre-existing test and the current frontend — which has no capability to
send an API key — continue to work completely unchanged. When
`AION_REQUIRE_AUTH=1` is set (a real deployment, once keys are provisioned
via `auth/store.py`), a missing or invalid `X-API-Key` header returns 401,
and role-based authorization becomes enforceable (see `require_role`).

Unauthenticated requests (when auth is not required) resolve to
`settings.default_tenant_id` — this is what gives every existing
single-tenant test and the frontend a consistent, real tenant_id for
Cognitive Memory isolation (memory/store.py), rather than leaving tenant_id
as an untracked None everywhere.
"""

from fastapi import Header, HTTPException

from auth.store import key_store
from config import settings
from models.auth import AuthenticatedPrincipal, Role


async def get_current_principal(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthenticatedPrincipal | None:
    if x_api_key is None:
        if settings.require_auth:
            raise HTTPException(status_code=401, detail="Missing API key.")
        return None  # auth not required in this deployment — caller proceeds unauthenticated

    record = key_store.resolve(x_api_key)
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key.")
    return AuthenticatedPrincipal(key_id=record.key_id, tenant_id=record.tenant_id, role=record.role)


def resolve_tenant_id(principal: AuthenticatedPrincipal | None) -> str:
    """The tenant_id to use for the current request, whether authenticated
    or not — always a real string, never None, so Cognitive Memory
    isolation has something concrete to scope by."""
    return principal.tenant_id if principal is not None else settings.default_tenant_id


def require_role(principal: AuthenticatedPrincipal | None, *, allowed: set[Role]) -> None:
    """Authorization check: raises 403 if an authenticated principal's role
    isn't in `allowed`. An unauthenticated principal (auth not required in
    this deployment) is never role-restricted — there is nothing to check
    a role against, and restricting it would silently break the existing
    frontend contract.
    """
    if principal is not None and principal.role not in allowed:
        raise HTTPException(status_code=403, detail="Your role does not permit this action.")
