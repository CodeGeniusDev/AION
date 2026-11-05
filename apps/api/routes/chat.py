from fastapi import APIRouter, Depends, HTTPException, Request

from auth.dependency import get_current_principal, require_role, resolve_tenant_id
from config import settings
from realtime.publishers import publish_conversation_updated, publish_task_updated
from memory.alert_store import AlertStore
from memory.conversation_store import ConversationStore, ConversationSummary
from models.auth import AuthenticatedPrincipal
from models.chat import ChatRequest, ChatResponse
from observability.logging_config import get_logger
from observability.rate_limiter import InMemoryRateLimiter
from orchestration.workflow_runner import WorkflowRunner
from security.redaction import redact_text

router = APIRouter(tags=["chat"])
workflow_runner = WorkflowRunner()
conversation_store = ConversationStore()

# Alert store shares the same db_path as memory store for consistent persistence.
# When AION_MEMORY_DB_PATH is set (e.g. Docker volume), alerts survive restarts.
alert_store = AlertStore(db_path=settings.memory_db_path or ":memory:")

# Seed a welcome alert so the notifications page is not empty on first load.
alert_store.create(
    title="Welcome to AION",
    description="AION is ready. Send a message in Chat to get started — task completions and system events will appear here.",
    category="system",
    tone="info",
)

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

    # Phase 1F: Secret Guard. Credentials are stripped at the request
    # boundary BEFORE anything downstream can observe the raw value —
    # conversation store, workflow runner (Gemini prompt, agents, bus,
    # memory), approval hook and alert previews all see only the
    # redacted text. Detection requires a secret-shaped value; ordinary
    # mentions ("password reset flow") pass through untouched.
    redaction = redact_text(payload.message)
    if redaction.redacted:
        payload = payload.model_copy(update={"message": redaction.text})
        logger.info(
            "chat_secret_redacted kinds=%s tenant_id=%s", list(redaction.labels), tenant_id,
        )

    # Load conversation history for multi-turn context
    history_context: list[str] = []
    if payload.conversation_id:
        stored = conversation_store.get_messages(payload.conversation_id)
        for msg in stored[-10:]:  # last 10 messages as context
            prefix = "User" if msg.role == "user" else "AION"
            history_context.append(f"{prefix}: {msg.content}")

    # Save user message before running the pipeline
    convo_id = payload.conversation_id or f"conversation-{__import__('uuid').uuid4().hex[:8]}"
    conversation_store.save_user_message(convo_id, payload.message)

    response = await workflow_runner.run(payload, available_memory=history_context or None, tenant_id=tenant_id)

    # Phase 2: chat-driven approval requests. A message asking for a
    # protected desktop action creates a PENDING approval only — this
    # path cannot approve, execute, or see grant tokens (see
    # services/chat_approval.py). Imported lazily because
    # services.approval_service back-references this module for alerts.
    try:
        from services.chat_approval import handle_chat_desktop_request
        pending = await handle_chat_desktop_request(
            payload.message, tenant_id=tenant_id,
            actor_key_id=principal.key_id if principal is not None else None,
        )
    except Exception:
        logger.exception("chat_approval_hook_failed")
        pending = None
    if pending is not None:
        response.pending_approval = pending
        response.answer = (
            f"⚠ Approval required: I queued a pending request ({pending.tool}) "
            f"— approve or reject it in the approval queue ({pending.queue_path}). "
            f"Nothing runs until a human approves.\n\n{response.answer}"
        )

    # Override the conversation_id with our persisted one
    response.conversation_id = convo_id

    # Phase 1F: tell the UI which credential kinds were removed. The
    # answer itself was generated from the redacted message only.
    response.warnings = [f"{kind} removed" for kind in redaction.labels]

    # Save assistant response
    if response.status == "completed":
        conversation_store.save_assistant_message(convo_id, response.answer, task_id=response.task_id)

    # Phase 2B: signal conversation and task updates to SSE subscribers.
    publish_conversation_updated(tenant_id, conversation_id=convo_id)
    publish_task_updated(tenant_id, task_id=response.task_id, status=response.status)

    # Auto-generate a notification alert for this task
    try:
        alert_store.create_task_alert(
            task_id=response.task_id,
            message_preview=payload.message,
            status=response.status,
        )
    except Exception:
        logger.warning("alert_creation_failed task_id=%s", response.task_id, exc_info=True)

    logger.info("chat_request_completed task_id=%s status=%s tenant_id=%s", response.task_id, response.status, tenant_id)
    return response


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(limit: int = 20) -> list[ConversationSummary]:
    """List recent conversations for the sidebar."""
    return conversation_store.list_conversations(limit=limit)


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str) -> list[dict]:
    """Load all messages for a conversation."""
    messages = conversation_store.get_messages(conversation_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return [
        {
            "message_id": m.message_id,
            "role": m.role,
            "content": m.content,
            "task_id": m.task_id,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str) -> dict:
    """Delete a conversation and all its messages."""
    deleted = conversation_store.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True, "conversation_id": conversation_id}
