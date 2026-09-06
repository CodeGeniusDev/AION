"""CognitiveMessage: the envelope carried by AION's Cognitive Bus.

Every field below has a concrete consumer, current or clearly near-term —
see the comment on each addition. Two fields deliberately considered and
NOT added:

  - a separate `uncertainty` field: `confidence` already exists and nothing
    in the system yet distinguishes "low confidence" from "high
    uncertainty" as separate concepts. Adding both without a consumer would
    be complexity for its own sake.
  - a `provenance` field on the message: `source_agent` already answers
    "who published this" at the granularity AION currently needs.
"""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

MessagePriority = Literal["low", "normal", "high"]


class CognitiveMessage(BaseModel):
    # Identity — needed so a single message can be retrieved directly
    # (`CognitiveBus.get_message`) and referenced by later messages.
    message_id: str = Field(default_factory=lambda: f"msg-{uuid4().hex[:12]}")

    # Correlation — task_id scopes a message to one task's cognitive
    # context (this is what makes task isolation possible). parent_message_id
    # is optional and records which prior message this one is responding to,
    # enabling `replay()` to show causal threads, not just a flat list.
    task_id: str
    parent_message_id: str | None = None

    source_agent: str
    # None means broadcast: the message is relevant to every subscriber of
    # the task, not one specific agent. Widened from `str` to `str | None` —
    # every existing caller passes a concrete string, so this is backward
    # compatible.
    target_agent: str | None = None

    intent: str
    content: str
    context: dict[str, Any] = Field(default_factory=dict)

    # References to prior evidence (e.g. memory entries, source ids) this
    # message relies on. Empty by default; populated once Cognitive Memory
    # (a later phase) has real entries to reference. Kept as opaque strings
    # rather than a typed object because the shape of "evidence" isn't
    # defined yet — that's Cognitive Memory's job, not the bus's.
    evidence_refs: list[str] = Field(default_factory=list)

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    priority: MessagePriority = "normal"
    status: Literal["pending", "processing", "completed", "failed"] = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
