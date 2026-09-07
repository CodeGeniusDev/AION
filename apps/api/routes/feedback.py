"""User feedback on chat responses.

Collects thumbs-up / thumbs-down signals with optional comments. Stored
in-memory for the process lifetime — a real deployment would persist to a
database for analytics. The endpoint always succeeds (never blocks the UI).
"""

import logging
from uuid import uuid4

from fastapi import APIRouter

from models.feedback import FeedbackRequest

router = APIRouter(tags=["feedback"])
logger = logging.getLogger("aion.feedback")

# Process-lifetime feedback store: list of all submitted feedback entries
_feedback_store: list[dict] = []


@router.post("/feedback")
async def submit_feedback(payload: FeedbackRequest) -> dict:
    entry = {
        "feedback_id": f"fb-{uuid4().hex[:8]}",
        "task_id": payload.task_id,
        "sentiment": payload.sentiment,
        "comment": payload.comment,
    }
    _feedback_store.append(entry)
    logger.info(
        "feedback_received task_id=%s sentiment=%s comment_len=%d",
        payload.task_id, payload.sentiment, len(payload.comment),
    )
    return {"accepted": True, "feedback_id": entry["feedback_id"]}
