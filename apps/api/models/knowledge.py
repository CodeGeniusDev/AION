"""Knowledge & Research schemas.

Named "knowledge.py" (not "research.py") to avoid colliding with the
pre-existing models/research.py, which backs the frontend's /api/research
demo endpoint — an unrelated, earlier concern (static research notes for
the dashboard UI), not part of this Cognitive-DNA-integrated Knowledge
Layer.

`EvidenceSource` carries real provenance always: provider, title, url
(nullable — internal sources genuinely have no URL), and a real retrieval
timestamp. `Evidence` is the normalized, verifiable unit built from a
source; its `verification_state` uses the same four-state vocabulary as
Cognitive Memory (models/cognitive_memory.py) and the Immune System
(models/verification.py) — deliberately not a fifth, incompatible scheme.

`ResearchResult.evidence` contains ONLY verified evidence — the trusted
output. `all_sources` retains everything actually retrieved, for
transparency about what was considered but not necessarily trusted.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

EvidenceVerificationState = Literal["unverified", "uncertain", "verified", "contradicted"]


class EvidenceSource(BaseModel):
    source_id: str
    provider: str
    title: str
    url: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_content: str


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"ev-{uuid4().hex[:10]}")
    task_id: str
    provider_id: str
    source: EvidenceSource
    content: str
    verification_state: EvidenceVerificationState = "unverified"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResearchConflict(BaseModel):
    evidence_a_id: str
    evidence_b_id: str
    description: str


class ResearchResult(BaseModel):
    query: str
    task_id: str
    evidence: list[Evidence] = Field(default_factory=list)  # verified only — the trusted output
    all_sources: list[EvidenceSource] = Field(default_factory=list)  # everything retrieved, for transparency
    conflicts: list[ResearchConflict] = Field(default_factory=list)
    provider_errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
