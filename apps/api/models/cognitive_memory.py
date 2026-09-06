"""Cognitive Memory schemas.

Three memory types, each with a distinct, justified purpose — not four
generic categories added for completeness:

  EPISODIC — "this happened": one record per completed task, a factual log
    of what AION did (agents used, decision, outcome). Never gated by
    verification, because it isn't a claim about the world — it's a record
    of AION's own execution.

  SEMANTIC — "this is known to be true, as far as AION can tell": reusable
    facts extracted from a task's output. Gated strictly by the Immune
    System (Phase E) — only claims with verification_state="verified" are
    ever written here. This is the "never blindly store unverified or
    contradicted claims" requirement, enforced structurally, not by policy
    alone (see memory/consolidation.py — the write path only ever calls
    immune.memory_policy.memory_candidates(), which filters to verified).

  TASK_CONTEXT — short-lived, per-request working memory (the `memories`
    list already threaded through WorkflowRunner/agents). Not a distinct
    storage type here; included in the enum for completeness with the
    architecture, since agents already receive this via `context["memories"]`.

verification_state deliberately keeps these states separate, per the
project's own instruction not to collapse "generated" / "supported" /
"verified" / "contradicted" / "unknown" into one signal:
  - "unverified": never evaluated for truth (episodic log entries).
  - "uncertain": evaluated, but evidence was insufficient or only partial.
  - "verified": evaluated and supported by available context.
  - "contradicted": evaluated and found to conflict with available context.
    (Contradicted claims are never written to memory in the first place —
    this state exists in the schema for completeness/traceability, not
    because contradicted content is ever persisted.)

confidence is intentionally `float | None`, defaulting to None: this
pipeline has no numeric per-claim confidence score anywhere (the Immune
System produces a status + risk level, not a probability), so no number is
invented here. The verification_state itself is the trust signal.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

MemoryType = Literal["episodic", "semantic", "task_context"]
MemoryVerificationState = Literal["unverified", "uncertain", "verified", "contradicted"]


class MemoryRecord(BaseModel):
    memory_id: str = Field(default_factory=lambda: f"mem-{uuid4().hex[:12]}")
    type: MemoryType
    content: str
    task_id: str
    source_agent: str
    verification_state: MemoryVerificationState
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    provenance: str
    # None means "untenanted" (legacy/shared data, e.g. records written
    # before authentication was configured, or by internal subsystems that
    # don't yet thread a tenant through — see memory/store.py's search()
    # for exact isolation semantics). A tenant-scoped search never returns
    # another tenant's records, but does not currently include untenanted
    # records either — isolation is strict by default.
    tenant_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MemorySearchResult(BaseModel):
    record: MemoryRecord
    relevance_score: float = Field(
        ge=0.0, le=1.0,
        description=(
            "Lexical word-overlap score against the query, NOT a semantic "
            "embedding similarity — no embedding provider is active by "
            "default (see memory/embeddings.py). This is a real, computed "
            "value, not invented, but it is a keyword heuristic and should "
            "be understood as one."
        ),
    )
