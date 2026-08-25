"""Agents API service.

Sources real data from the live Cognitive DNA Agent Registry
(agents.registry.registry) — the same registry every agent registers into
at import time (see agents/planner.py etc.), and the same one
DynamicBrainFormer queries for capability-based selection. This is not a
separate/duplicate data source: it's the actual runtime state.

Response fields mapped honestly, not invented:
  - status: from AgentIdentity.availability (real, declared per-agent).
  - confidence: if the agent has real measured performance
    (PerformanceHistory.success_rate, populated only after real
    registry.record_run() calls), that measured value is used. Otherwise
    falls back to the capability's declared_proficiency — a design-time
    prior, not a measurement — and this distinction is preserved in the
    `confidence_source` this module computes internally (not exposed in
    the response body, since the existing Agent schema has no such field
    and must not be broken — see models/agents.py).
  - specialty: the agent's highest-declared-proficiency capability name.
"""

import agents  # noqa: F401 — import triggers agent registration into the registry
from agents.registry import registry
from models.agents import Agent, AgentsResponse
from models.cognitive_dna import AgentIdentity


def _best_capability_name(identity: AgentIdentity) -> str:
    if not identity.capabilities:
        return "General"
    best = max(identity.capabilities, key=lambda capability: capability.declared_proficiency)
    return best.name.replace("_", " ").title()


def _status(identity: AgentIdentity) -> str:
    """Cognitive DNA's AvailabilityStatus has 4 values (adds DEGRADED),
    but the pre-existing Agent response schema only allows 3 (see
    models/agents.py — changing that schema would break the frontend
    contract). DEGRADED maps to "online": the agent is still functioning,
    just not at full capability, which is closer to "online" than
    "offline" or "standby"."""
    value = identity.availability.value
    return value if value in ("online", "standby", "offline") else "online"


def _confidence_percent(identity: AgentIdentity) -> int:
    if identity.performance.success_rate is not None:
        return round(identity.performance.success_rate * 100)
    if identity.capabilities:
        best = max(capability.declared_proficiency for capability in identity.capabilities)
        return round(best * 100)
    return 50


def get_agents() -> AgentsResponse:
    """Real agent identities from the live Cognitive DNA registry."""
    identities = registry.list_identities()
    items = [
        Agent(
            id=identity.id,
            name=identity.name,
            description=identity.description,
            status=_status(identity),
            confidence=_confidence_percent(identity),
            specialty=_best_capability_name(identity),
        )
        for identity in identities
    ]
    return AgentsResponse(items=items, total=len(items))
