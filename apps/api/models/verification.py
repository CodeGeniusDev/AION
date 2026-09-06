"""Verification / AI Immune System schemas.

Deliberately distinct from the Critic's concerns: the Critic asks "is this
response well-written and internally coherent?" — a quality check on prose.
The Immune System asks "can this claim be trusted given the evidence AION
actually has access to?" — a trust check on individual claims. Different
questions, different data. This module does not import or reuse anything
from agents/critic.py.

Evidence limitation, stated plainly: AION currently has no external fact
source. "Evidence" here means only (a) memory strings supplied with the
request, and (b) other agents' outputs from the same task. This is internal
cross-consistency checking, not independent real-world fact verification —
the system never claims to be the latter.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

VerificationStatus = Literal["verified", "partially_verified", "contradicted", "insufficient_evidence"]
RiskLevel = Literal["low", "medium", "high", "critical"]
ImmuneDecision = Literal["pass", "pass_with_warning", "require_revision", "reject"]
EvidenceRelation = Literal["supports", "contradicts"]


class ClaimRecord(BaseModel):
    claim_id: str = Field(default_factory=lambda: f"claim-{uuid4().hex[:8]}")
    text: str
    source_agent: str
    task_id: str


class EvidenceRef(BaseModel):
    content: str
    source: str  # "memory" or "agent:<id>"
    relation: EvidenceRelation


class VerificationResult(BaseModel):
    claim: ClaimRecord
    status: VerificationStatus
    supporting_evidence: list[EvidenceRef] = Field(default_factory=list)
    contradicting_evidence: list[EvidenceRef] = Field(default_factory=list)
    risk: RiskLevel
    verifier: str = "aion-immune-v1"
    reasoning_summary: str
    verifier_failed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ImmuneReport(BaseModel):
    task_id: str
    claims_checked: int
    verification_results: list[VerificationResult] = Field(default_factory=list)
    decision: ImmuneDecision
    decision_reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
