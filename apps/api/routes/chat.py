from fastapi import APIRouter, Depends, HTTPException, Request

from auth.dependency import get_current_principal, require_role, resolve_tenant_id
from config import settings
from models.auth import AuthenticatedPrincipal
from models.chat import ChatRequest, ChatResponse
from observability.logging_config import get_logger
from observability.rate_limiter import InMemoryRateLimiter
from orchestration.workflow_runner import WorkflowRunner

router = APIRouter(tags=["chat"])
workflow_runner = WorkflowRunner()
logger = get_logger("routes.chat")

# Rate limiting on /api/chat only — the only compute-heavy endpoint.
# In-memory, single-process (see observability/rate_limiter.py); genuinely
# functional today, replaceable with a distributed implementation later
# without changing this call site.
_rate_limiter = InMemoryRateLimiter(
    max_requests=settings.rate_limit_requests, window_seconds=settings.rate_limit_window_seconds,
)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest, request: Request,
    principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
) -> ChatResponse:
    # Authorization: "readonly" keys may not invoke chat (it writes to
    # Cognitive Memory). No-op when unauthenticated (settings.require_auth
    # is False) — never restricts the existing frontend, which sends no key.
    require_role(principal, allowed={"admin", "user"})

    # Rate limit key: per authenticated key when available (fairer — one
    # tenant's traffic can't exhaust another's budget), else per client IP.
    rate_limit_key = principal.key_id if principal else (request.client.host if request.client else "unknown")
    if not _rate_limiter.allow(rate_limit_key):
        logger.warning("rate_limit_exceeded key=%s", rate_limit_key)
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down and try again shortly.")

    tenant_id = resolve_tenant_id(principal)
    logger.info("chat_request_received mode=%s tenant_id=%s authenticated=%s", payload.mode, tenant_id, principal is not None)
    response = await workflow_runner.run(payload, tenant_id=tenant_id)
    logger.info("chat_request_completed task_id=%s status=%s tenant_id=%s", response.task_id, response.status, tenant_id)
    return response
