"""Cognitive DNA: the machine-readable, declarative identity of an AION agent.

Design intent
-------------
These models describe WHAT an agent is (capabilities, dependencies, limits,
trust) so other AION subsystems — Agent Registry now, Dynamic Brain Formation,
Cognitive Memory, and the Verification/Immune layer later — can reason about
agents without importing or executing their code.

Hard rule: nothing in this module executes agent behavior. `AgentIdentity` is
pure data. Execution stays in `agents.base.BaseAgent` and its subclasses.

Declared vs. measured
----------------------
`CapabilityTag.declared_proficiency` is a self-declared prior set by whoever
defines the agent (a design-time claim, e.g. "this agent should be decent at
task decomposition"). `PerformanceHistory` is the measured record of what
actually happened at runtime. The two are kept as separate fields so a future
calibration step (Phase F, Evaluation) can compare declared vs. measured and
detect miscalibrated agents — conflating them would make that comparison
impossible.

No invented numbers: every `PerformanceHistory` field defaults to zero/None
and is only ever populated by `AgentRegistry.record_run()` after a real
execution. Nothing in this file fabricates confidence, latency, or cost data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Domain(str, Enum):
    """Broad subject-matter area an agent's capabilities fall under.

    Intentionally a small, closed set today, matching AION's four current
    agents. New domains are added here as new agent types are introduced —
    this enum is the vocabulary Dynamic Brain Formation will later query.
    """

    PLANNING = "planning"
    RESEARCH = "research"
    REVIEW = "review"
    MEMORY = "memory"
    GENERAL = "general"
    COMPUTATION = "computation"  # added for the Tool System: deterministic utility tools (e.g. calculation, text analysis) that don't fit the four agent domains


class AvailabilityStatus(str, Enum):
    """Runtime availability. Superset of the current agents' `status` values
    (online/standby/offline) so existing behavior maps in without loss."""

    ONLINE = "online"
    STANDBY = "standby"
    OFFLINE = "offline"
    DEGRADED = "degraded"  # model dependency unreachable but a fallback path still works


class CapabilityTag(BaseModel):
    """One discrete, declared thing an agent claims it can do.

    `declared_proficiency` is a design-time prior, not a measured accuracy.
    It exists so Dynamic Brain Formation has *something* to rank candidates
    by before any performance history accumulates. Once `PerformanceHistory`
    has real data, later phases can compare the two and recalibrate.
    """

    name: str
    domain: Domain
    declared_proficiency: float = Field(
        ge=0.0, le=1.0, default=0.5,
        description="Self-declared prior confidence in this capability, not a measured accuracy.",
    )
    description: str = ""


class ModelDependency(BaseModel):
    """What backing model/provider this agent needs to operate at full capability."""

    provider: str  # e.g. "gemini"; "none" for agents with no model dependency
    model: str | None = None
    required: bool = Field(
        default=False,
        description="If False, the agent has a meaningful deterministic fallback and can run without this dependency.",
    )


class SafetyConstraint(BaseModel):
    """Declarative limits, read by future verification/immune-layer code.

    This model does not enforce anything itself — it is metadata that a
    future verification subsystem consults.
    """

    max_output_tokens: int | None = None
    disallowed_domains: list[Domain] = Field(default_factory=list)
    requires_verification: bool = False


class PerformanceHistory(BaseModel):
    """Measured, mutable execution record. Empty until real runs occur.

    Every field starts at zero/None. This model is only ever updated by
    `AgentRegistry.record_run()` from an actual completed or failed agent
    step — never pre-populated with assumed values.
    """

    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    average_confidence: float | None = None
    average_latency_ms: float | None = None
    last_run_at: datetime | None = None

    @property
    def success_rate(self) -> float | None:
        return self.successful_runs / self.total_runs if self.total_runs else None

    def is_consistent(self) -> bool:
        """Invariant check: completed + failed runs can never exceed total runs."""
        return self.successful_runs + self.failed_runs <= self.total_runs


class AgentIdentity(BaseModel):
    """Machine-readable cognitive identity of one agent.

    One identity per agent CLASS/version, not per request or per instance.
    Purely declarative — see module docstring. `id` must match the owning
    `BaseAgent.id` for the four current agents; this is enforced by
    `AgentRegistry.register()`, not by this schema, so that future
    third-party agents (which won't subclass `BaseAgent` the same way) can
    still be represented.
    """

    id: str
    name: str
    version: str = "1.0.0"
    description: str
    capabilities: list[CapabilityTag] = Field(min_length=1)
    domains: list[Domain] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)
    model_dependency: ModelDependency
    tools: list[str] = Field(default_factory=list)
    safety: SafetyConstraint = Field(default_factory=SafetyConstraint)
    availability: AvailabilityStatus = AvailabilityStatus.ONLINE
    performance: PerformanceHistory = Field(default_factory=PerformanceHistory)
    provenance: str = "aion-core"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
