"""Dynamic Brain: the traceable RESULT of one task's capability-driven agent
selection. This module is purely declarative — it records what was decided
and why. The reasoning itself lives in orchestration/brain_former.py.

A Brain answers the question Phase C requires: "what agents were selected,
why were they selected, and what capabilities did they provide?"
"""

from pydantic import BaseModel, Field

from models.chat import AgentId
from models.cognitive_dna import Domain


class AgentSelection(BaseModel):
    """One agent's inclusion in a formed brain, with the reasoning behind it.

    `domain` and `matched_capability` are None for selections that didn't
    come from capability matching — manual-mode (user picked the agent
    directly) and legacy-router fallback (keyword match, not a domain).
    `measured_success_rate` is None whenever the agent has no recorded runs
    yet; it is never fabricated to look more complete than it is.
    """

    agent_id: AgentId
    domain: Domain | None = None
    matched_capability: str | None = None
    declared_proficiency: float | None = Field(default=None, ge=0.0, le=1.0)
    measured_success_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str


class Brain(BaseModel):
    """A temporary, task-specific cognitive network formed for one request.

    `used_fallback=True` means capability discovery could not confidently
    form a brain (some required domain had zero available agents) and
    execution fell back to the legacy keyword AgentRouter instead — this is
    always observable here, never silent.
    """

    task_id: str
    mode: str
    required_domains: list[Domain] = Field(default_factory=list)
    candidates_considered: list[str] = Field(default_factory=list)
    selected_agents: list[AgentSelection] = Field(default_factory=list)
    execution_order: list[AgentId] = Field(default_factory=list)
    formation_reason: str
    used_fallback: bool = False
    fallback_reason: str | None = None
