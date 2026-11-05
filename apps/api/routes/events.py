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


@router.get("/events")
async def stream_global_events(max_events: int | None = None):
    """Stream global Cognitive Bus events across all tasks and subsystems.

    Powers the real-time command center dashboard. Subscribes to the
    'global' topic on the Cognitive Bus, streaming live system, task,
    agent, and memory lifecycle events with periodic keepalives.
    """
    bus = workflow_runner.bus
    queue: asyncio.Queue[CognitiveMessage | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_message(message: CognitiveMessage) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, message)

    sub_id = bus.subscribe("global", on_message)

    async def event_generator():
        emitted = 0
        try:
            from datetime import datetime, timezone
            yield f"data: {json.dumps({'type': 'connected', 'service': 'AION API', 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
            emitted += 1
            if max_events is not None and emitted >= max_events:
                return

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if message is None:
                    break

                event_data = {
                    "type": "event",
                    "event": message.intent,
                    "message_id": message.message_id,
                    "task_id": message.task_id,
                    "source_agent": message.source_agent,
                    "target_agent": message.target_agent,
                    "intent": message.intent,
                    "content": message.content,
                    "status": message.status,
                    "confidence": message.confidence,
                    "context": message.context,
                    "created_at": message.created_at.isoformat(),
                }
                yield f"data: {json.dumps(event_data)}\n\n"
                emitted += 1
                if max_events is not None and emitted >= max_events:
                    break
        finally:
            bus.unsubscribe(sub_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
