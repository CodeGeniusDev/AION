"""SSE endpoint for real-time agent progress streaming.

The Cognitive Bus already records every per-agent event during workflow
execution. This module bridges those events to the frontend via Server-Sent
Events (SSE), replacing the fake ProcessingState timer with genuine progress
data.

Flow:
  1. Frontend sends POST /api/chat
  2. Chat route generates task_id, starts workflow in background
  3. Frontend opens GET /api/events/{task_id}
  4. SSE endpoint subscribes to the bus topic and streams events
  5. Connection closes when the task completes
"""

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from cognitive_bus.schema import CognitiveMessage
from routes.chat import workflow_runner

router = APIRouter(tags=["events"])


@router.get("/events/{task_id}")
async def stream_task_events(task_id: str):
    """Stream Cognitive Bus events for a task as SSE.

    Connects to the bus, replays any events that already happened (so
    the frontend doesn't miss early events if it connects slightly late),
    then streams new events in real time until a terminal status is seen.
    """
    bus = workflow_runner.bus
    queue: asyncio.Queue[CognitiveMessage | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_message(message: CognitiveMessage) -> None:
        """Bus subscriber callback — runs on the bus's thread, so we use
        call_soon_threadsafe to push into the async queue."""
        loop.call_soon_threadsafe(queue.put_nowait, message)

    # Subscribe to all events for this task
    sub_id = bus.subscribe(f"task:{task_id}", on_message)

    # Replay events that already happened before we subscribed
    existing = bus.get_task_messages(task_id)
    seen_ids: set[str] = set()
    for msg in existing:
        await queue.put(msg)
        seen_ids.add(msg.message_id)

    async def event_generator():
        try:
            # Send initial connection event
            yield f"data: {json.dumps({'type': 'connected', 'task_id': task_id})}\n\n"

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=60.0)
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
                    continue

                if message is None:
                    break

                # Skip duplicates from replay
                if message.message_id in seen_ids:
                    continue
                seen_ids.add(message.message_id)

                event_data = {
                    "type": "agent_event",
                    "message_id": message.message_id,
                    "source_agent": message.source_agent,
                    "target_agent": message.target_agent,
                    "intent": message.intent,
                    "content": message.content,
                    "status": message.status,
                    "confidence": message.confidence,
                }
                yield f"data: {json.dumps(event_data)}\n\n"

                # Terminal statuses — close the stream
                if message.status in ("completed", "failed") and message.intent in (
                    "task_completed", "task_failed", "memory_write", "memory_write_failed",
                    "immune_decision",
                ):
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break

        finally:
            bus.unsubscribe(sub_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
