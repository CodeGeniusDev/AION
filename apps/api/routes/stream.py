"""GET /api/stream — tenant-scoped SSE for real-time business events.

Reuses the existing auth pattern (opt-in via AION_REQUIRE_AUTH); resolves
tenant_id the same way every other /api route does. Accepts the standard
Last-Event-ID header for reconnect resume.

Design:
- The hub is a module-level singleton wired during app lifespan.
- On connect, the client subscribes with optional last_event_id; the hub
  replays buffered events, then yields live events with a 15 s heartbeat.
- On disconnect (CancelledError), the subscriber is removed cleanly.
- The route never blocks the approval gate or any other write path.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from auth.dependency import get_current_principal, resolve_tenant_id
from realtime import EventType, get_hub
from models.auth import AuthenticatedPrincipal

router = APIRouter(tags=["stream"])


@router.get("/stream")
async def event_stream(
    request: Request,
    principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    """Server-Sent Events stream of tenant-scoped business events.

    Emits heartbeat comments every 15 s to keep proxies from closing the
    connection. Returns 503 if the connection cap is reached.
    """
    tenant_id = resolve_tenant_id(principal)
    hub = get_hub()

    resume_id: int | None = None
    if last_event_id is not None:
        try:
            resume_id = int(last_event_id)
        except (ValueError, TypeError):
            resume_id = None

    client = hub.subscribe(tenant_id, last_event_id=resume_id)
    if client is None:
        return StreamingResponse(
            iter(["retry: 5000\n\n"]),
            status_code=503,
            media_type="text/event-stream",
            headers={"X-AION-Reason": "connection-cap-reached"},
        )

    async def generate():
        try:
            # Initial connected frame (not a real event — helps the client
            # know the SSE channel is live before the first business event).
            yield "event: connected\ndata: {}\n\n"
            async for evt in hub.stream(client):
                # Check if client disconnected mid-yield.
                if await request.is_disconnected():
                    break
                if evt.type == EventType.RESYNC and evt.payload.get("heartbeat"):
                    # Heartbeat comment (not a real event frame).
                    yield ": heartbeat\n\n"
                else:
                    yield evt.sse_frame()
        finally:
            hub.unsubscribe(client)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
