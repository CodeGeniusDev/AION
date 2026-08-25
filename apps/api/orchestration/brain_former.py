"""Dynamic Brain Formation.

Replaces AION's fixed keyword-to-agent-id mapping (AgentRouter, still kept
as the baseline/fallback) with a two-step, capability-driven process for
auto-mode requests:

  1. Task capability extraction — infer which Cognitive DNA `Domain`s a
     message needs, deterministically, from phrase matching. No LLM call:
     Phase C's brief is explicit that routing should stay deterministic and
     testable, not "look intelligent" via an extra model call.
  2. Candidate discovery + selection — ask the AgentRegistry which
     currently-available agents declare each required domain, score them by
     declared proficiency (a design-time prior) and, where it exists,
     measured performance history (success_rate — real data only, never
     invented), and select deterministically.

quick/manual/research modes represent explicit user intent, not inferred
task understanding, so they are honored as given rather than re-derived
from keywords:
  - quick: no agents, by definition.
  - manual: the user's exact selection, unchanged.
  - research: a fixed, well-known team (planning + research + review) —
    this is a deliberate, explicit request for thoroughness, not something
    to second-guess with keyword inference.

Only auto mode performs real capability inference.

Fallback: if a required domain has zero available agents, brain formation
cannot confidently proceed — it falls back to AgentRouter's keyword
routing for the *entire* decision (not a partial mix) and marks
`Brain.used_fallback=True` with a reason, so the fallback is always
observable in the response trace, never silent.
"""

from dataclasses import dataclass

from agents.registry import AgentRegistryInterface
from agents.registry import registry as default_registry
from models.brain import AgentSelection, Brain
from models.chat import AgentId, ChatMode
from models.cognitive_dna import AgentIdentity, AvailabilityStatus, Domain
from orchestration.agent_router import AgentRouter, RoutingDecision

# Deliberately mirrors AgentRouter.intent_phrases' vocabulary — this is the
# same deterministic phrase-matching approach, just mapped to Cognitive DNA
# domains instead of directly to agent ids. That is the actual architectural
# change: "research" no longer means "researcher" by name, it means the
# RESEARCH domain, which the AgentRegistry then resolves to whichever agent
# currently declares it.
DOMAIN_PHRASES: dict[Domain, set[str]] = {
    Domain.PLANNING: {"plan", "roadmap", "steps", "strategy", "schedule", "mansuba", "bana do", "tarteeb"},
    Domain.RESEARCH: {"research", "compare", "analyze", "analyse", "investigate", "find information", "tehqeeq", "muqabla", "maloomat"},
    Domain.REVIEW: {"check", "review", "verify", "correct", "is this right", "jaiza", "tasdeeq", "sahi hai"},
    Domain.MEMORY: {"remember", "previous", "earlier", "saved", "last time", "yaad", "pehle", "pichla"},
}

# Not a capability domain by itself — a modifier that, combined with a
# research-style request, signals the task benefits from prior context too.
COMPLEXITY_PHRASES = {"detailed", "comprehensive", "deep", "in-depth", "future", "mukammal", "tafseeli"}

# Execution order, not selection priority: once domains are chosen, this is
# the sequence they run in (plan before researching, research before
# reviewing, review before recalling memory). Not derived from anything
# measured — it is a structural ordering decision, documented as such.
DOMAIN_EXECUTION_PRIORITY: dict[Domain, int] = {
    Domain.PLANNING: 0,
    Domain.RESEARCH: 1,
    Domain.REVIEW: 2,
    Domain.MEMORY: 3,
    Domain.GENERAL: 4,
}


@dataclass
class _ScoredCandidate:
    identity: AgentIdentity
    capability_name: str
    declared_proficiency: float


class DynamicBrainFormer:
    def __init__(
        self,
        *,
        agent_registry: AgentRegistryInterface | None = None,
        router: AgentRouter | None = None,
    ) -> None:
        self.registry = agent_registry or default_registry
        self.router = router or AgentRouter()

    def form(
        self,
        *,
        task_id: str,
        message: str,
        mode: ChatMode,
        selected_agents: list[AgentId],
        available_memory: list[str],
        memory_enabled: bool,
    ) -> Brain:
        if mode == "quick":
            return Brain(task_id=task_id, mode=mode, formation_reason="Quick Answer uses a direct AION response.")

        if mode == "manual":
            selections = [
                AgentSelection(agent_id=agent_id, reason="Manually selected by the user")
                for agent_id in selected_agents
            ]
            return Brain(
                task_id=task_id,
                mode=mode,
                selected_agents=selections,
                execution_order=list(selected_agents),
                formation_reason="Agents were selected manually.",
            )

        if mode == "research":
            domains = [Domain.PLANNING, Domain.RESEARCH, Domain.REVIEW]
            if memory_enabled and available_memory:
                domains.append(Domain.MEMORY)
            return self._form_from_domains(
                task_id=task_id, mode=mode, domains=domains,
                base_reason="Research Team uses planning, research, and verification.",
                message=message, selected_agents=selected_agents,
                available_memory=available_memory, memory_enabled=memory_enabled,
            )

        # auto: the only mode that performs real capability inference
        domains = self._extract_required_domains(message, memory_enabled, available_memory)
        if not domains:
            return Brain(
                task_id=task_id, mode=mode,
                formation_reason="The request is simple enough for a direct AION response.",
            )

        return self._form_from_domains(
            task_id=task_id, mode=mode, domains=list(domains), base_reason=None,
            message=message, selected_agents=selected_agents,
            available_memory=available_memory, memory_enabled=memory_enabled,
        )

    @staticmethod
    def _extract_required_domains(message: str, memory_enabled: bool, available_memory: list[str]) -> set[Domain]:
        normalized = " ".join(message.casefold().split())
        matched = {domain for domain, phrases in DOMAIN_PHRASES.items() if any(phrase in normalized for phrase in phrases)}

        if Domain.MEMORY in matched and not memory_enabled:
            matched.discard(Domain.MEMORY)

        # A research-style request implies the planning + review domains
        # too, mirroring the legacy router's bundling of the "research team".
        if Domain.RESEARCH in matched:
            matched.add(Domain.PLANNING)
            matched.add(Domain.REVIEW)

        is_complex = any(phrase in normalized for phrase in COMPLEXITY_PHRASES)
        if is_complex and Domain.RESEARCH in matched and memory_enabled and available_memory:
            matched.add(Domain.MEMORY)

        return matched

    def _form_from_domains(
        self, *, task_id: str, mode: str, domains: list[Domain], base_reason: str | None,
        message: str, selected_agents: list[AgentId], available_memory: list[str], memory_enabled: bool,
    ) -> Brain:
        ordered_domains = sorted(set(domains), key=lambda domain: DOMAIN_EXECUTION_PRIORITY.get(domain, 99))
        selections: list[AgentSelection] = []
        considered: list[str] = []
        seen_agent_ids: set[str] = set()

        for domain in ordered_domains:
            candidates = self._candidates_for(domain)
            considered.extend(identity.id for identity in candidates)

            if not candidates:
                fallback_decision = self.router.route(message, mode, selected_agents, available_memory, memory_enabled)
                return self._fallback_brain(
                    task_id=task_id, mode=mode, domains=ordered_domains, considered=considered,
                    fallback_decision=fallback_decision,
                    fallback_reason=f"No available agent declares the '{domain.value}' capability domain.",
                )

            best = self._select_best(candidates, domain)
            if best.identity.id in seen_agent_ids:
                continue
            seen_agent_ids.add(best.identity.id)
            selections.append(AgentSelection(
                agent_id=best.identity.id,
                domain=domain,
                matched_capability=best.capability_name,
                declared_proficiency=best.declared_proficiency,
                measured_success_rate=best.identity.performance.success_rate,
                reason=(
                    f"Selected for '{domain.value}' via capability '{best.capability_name}' "
                    f"(declared proficiency {best.declared_proficiency:.2f})."
                ),
            ))

        execution_order = [selection.agent_id for selection in selections]
        reason = base_reason or self._describe_selection(selections)
        return Brain(
            task_id=task_id, mode=mode, required_domains=ordered_domains, candidates_considered=considered,
            selected_agents=selections, execution_order=execution_order, formation_reason=reason,
        )

    def _candidates_for(self, domain: Domain) -> list[AgentIdentity]:
        """Candidates for a domain, excluding only genuinely OFFLINE agents.

        Note this deliberately uses a broader availability filter than
        AgentRegistry.find_by_capability's own `available_only=True`
        default (which only accepts ONLINE/DEGRADED). STANDBY means "idle
        but ready" for an agent like the critic — a legitimate selection
        candidate, not an unavailable one. Only OFFLINE genuinely excludes
        an agent from Brain Formation.
        """
        return [
            identity
            for identity in self.registry.find_by_capability(domain=domain, available_only=False)
            if identity.availability != AvailabilityStatus.OFFLINE
        ]

    @staticmethod
    def _select_best(candidates: list[AgentIdentity], domain: Domain) -> _ScoredCandidate:
        scored = []
        for identity in candidates:
            domain_capabilities = [capability for capability in identity.capabilities if capability.domain == domain]
            best_capability = max(domain_capabilities, key=lambda capability: capability.declared_proficiency)
            scored.append(_ScoredCandidate(
                identity=identity,
                capability_name=best_capability.name,
                declared_proficiency=best_capability.declared_proficiency,
            ))

        # Deterministic ranking: declared proficiency first (the design-time
        # prior), then measured success_rate where it exists — an agent with
        # no run history yet is treated as neutral (0.5), neither rewarded
        # nor penalized for lacking data — then agent id as a final,
        # stable tiebreaker.
        scored.sort(
            key=lambda candidate: (
                -candidate.declared_proficiency,
                -(candidate.identity.performance.success_rate
                  if candidate.identity.performance.success_rate is not None else 0.5),
                candidate.identity.id,
            )
        )
        return scored[0]

    @staticmethod
    def _describe_selection(selections: list[AgentSelection]) -> str:
        if not selections:
            return "No capable agents were found for this request."
        names = ", ".join(f"{selection.agent_id} ({selection.domain.value})" for selection in selections)
        return f"AION formed a brain from capability matches: {names}."

    @staticmethod
    def _fallback_brain(
        *, task_id: str, mode: str, domains: list[Domain], considered: list[str],
        fallback_decision: RoutingDecision, fallback_reason: str,
    ) -> Brain:
        selections = [
            AgentSelection(agent_id=agent_id, reason="Selected via the legacy keyword router (fallback).")
            for agent_id in fallback_decision.execution_order
        ]
        return Brain(
            task_id=task_id, mode=mode, required_domains=domains, candidates_considered=considered,
            selected_agents=selections, execution_order=fallback_decision.execution_order,
            formation_reason=fallback_decision.reason, used_fallback=True, fallback_reason=fallback_reason,
        )


def brain_to_routing_decision(brain: Brain) -> RoutingDecision:
    """Adapter so WorkflowRunner's existing loop (which consumes
    RoutingDecision) needs no structural changes to work with a Brain."""
    return RoutingDecision(
        selected_agents=list(brain.execution_order),
        reason=brain.formation_reason,
        execution_order=list(brain.execution_order),
    )
