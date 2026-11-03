"""Test-only fixture endpoints — Phase 2A deterministic E2E setup.

These routes are the ONLY sanctioned way for the Playwright suite (and
any future black-box E2E runner) to create the exact state a test needs
without seeding the developer's real database. They are wired into the
SAME singletons the real routes use — a task created here is the row
GET /api/tasks returns, an alert created here is what the bell popover
lists. Nothing bypasses tenant scoping, redaction or validation, and no
handler writes to any store outside the process-wide SQLite files.

Guard: the router is registered ONLY when ``AION_TEST_MODE=1`` is set in
the API environment. When the flag is off the module still imports
cheaply (for tests that assert 404 behaviour), but every endpoint raises
HTTPException(404) with the same generic detail the app's global
exception handler uses for unknown routes. In production the flag is
never set, so the endpoints are effectively absent.

Design contract for the frontend suite:
- ``POST /api/_test/reset`` — clears every row these helpers create.
- ``POST /api/_test/seed/task`` — real ``Task`` row via ``task_service``.
- ``POST /api/_test/seed/alert`` — real ``AlertItem`` via ``AlertStore``.
- ``POST /api/_test/seed/conversation`` — real conversation + messages.
- ``POST /api/_test/seed/profile`` — real profile row (or ``null`` to clear).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/_test", tags=["test-fixture"])


def _require_test_mode() -> None:
    """Raise 404 unless this process booted with AION_TEST_MODE=1.

    The check runs per-request rather than at import so the module can
    always be included and a test can assert the absent case honestly.
    """
    if os.environ.get("AION_TEST_MODE") != "1":
        # Same message shape as the global 404 handler so a caller
        # cannot tell these routes from any unknown path.
        raise HTTPException(status_code=404, detail="Not Found")


class SeedTask(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    agent: str = "aion"
    status: str = "pending"


class SeedAlert(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: str = "system"
    tone: str = "info"
    link: str | None = None


class SeedConversation(BaseModel):
    conversation_id: str | None = None
    user_message: str = Field(min_length=1, max_length=500)
    assistant_message: str | None = None
    task_id: str | None = None


class SeedProfile(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)
    username: str = Field(min_length=1, max_length=40)
    email: str = ""
    role: str = ""
    timezone: str = "UTC"
    bio: str = ""
    avatar_color: str = "navy"


@router.post("/reset")
async def reset_test_state() -> dict[str, Any]:
    """Delete every row the seeding helpers create.

    Does NOT touch:
    - Memory store records written by real chats (those go through the
      same consolidation path as production, and clearing them would
      hide real bugs).
    - Approval ledger rows — those are the security-critical state;
      tests that need approvals create real ones through chat/desktop.
    """
    _require_test_mode()

    from memory.alert_store import AlertStore  # noqa: F401 (type hint)
    from memory.conversation_store import ConversationStore
    from memory.profile_store import get_default_profile_store
    from memory.task_store import get_default_task_store
    from routes.chat import alert_store, conversation_store

    # Tasks: the store has a delete by id; clear via list_all + delete
    # to avoid raw SQL that could drift from the schema.
    task_store = get_default_task_store()
    for task in task_store.list_all():
        task_store.delete(task.id)

    # Alerts: same pattern — no bulk-delete API on the store, use SQL
    # guarded by the test-mode flag. This NEVER runs against the
    # production process (AION_TEST_MODE is not set there).
    with alert_store._cursor() as cursor:  # noqa: SLF001 (test-only)
        cursor.execute("DELETE FROM alerts")

    # Conversations: the store exposes delete per conversation.
    convo_store: ConversationStore = conversation_store
    for summary in convo_store.list_conversations(limit=1000):
        convo_store.delete_conversation(summary.conversation_id)

    # Profile + settings: one-row table + key/value table.
    profile_store = get_default_profile_store()
    with profile_store._cursor() as cursor:  # noqa: SLF001 (test-only)
        cursor.execute("DELETE FROM profile")
        cursor.execute("DELETE FROM settings")

    return {
        "reset": True,
        "cleared": ["tasks", "alerts", "conversations", "profile", "settings"],
    }


@router.post("/seed/task")
async def seed_task(payload: SeedTask) -> dict[str, Any]:
    _require_test_mode()
    from models.tasks import Task  # local import to avoid a cycle at boot
    from memory.task_store import get_default_task_store

    valid = {"pending", "pending_approval", "running", "completed", "failed"}
    if payload.status not in valid:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(valid)}")

    store = get_default_task_store()
    task = Task(
        id=f"test-{os.urandom(6).hex()}",
        title=payload.title,
        agent=payload.agent,
        status=payload.status,  # type: ignore[arg-type]
        confidence=0,
        output=None,
        created="",
        updated="",
    )
    created = store.create(task)
    return created.model_dump()


@router.post("/seed/alert")
async def seed_alert(payload: SeedAlert) -> dict[str, Any]:
    _require_test_mode()
    from routes.chat import alert_store

    return alert_store.create(
        title=payload.title,
        description=payload.description,
        category=payload.category,
        tone=payload.tone,
        link=payload.link,
    )


@router.post("/seed/conversation")
async def seed_conversation(payload: SeedConversation) -> dict[str, Any]:
    _require_test_mode()
    from routes.chat import conversation_store

    convo_id = payload.conversation_id or f"conv-{os.urandom(6).hex()}"
    user = conversation_store.save_user_message(
        convo_id, payload.user_message, title=payload.user_message[:60],
    )
    assistant = None
    if payload.assistant_message is not None:
        assistant = conversation_store.save_assistant_message(
            convo_id, payload.assistant_message, task_id=payload.task_id or "none",
        )
    return {
        "conversation_id": convo_id,
        "user": user.model_dump(),
        "assistant": assistant.model_dump() if assistant else None,
    }


@router.post("/seed/profile")
async def seed_profile(payload: SeedProfile) -> dict[str, Any]:
    _require_test_mode()
    from memory.profile_store import get_default_profile_store

    store = get_default_profile_store()
    return store.upsert_profile(payload.model_dump())
