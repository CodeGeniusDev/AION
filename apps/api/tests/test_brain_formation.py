"""Tests for Dynamic Brain Formation (orchestration/brain_former.py).

Covers capability extraction, candidate discovery, proficiency/availability
filtering, single- and multi-agent brain formation, fallback to the legacy
router, deterministic selection, and execution through the Cognitive Bus.
WorkflowRunner-level regression against previous routing behavior lives in
test_chat_orchestration.py (unmodified — all 9 tests there still pass
unchanged, which is itself the regression proof for this phase).
"""

import asyncio

from agents.registry import AgentRegistry
from models.chat import ChatRequest
from models.cognitive_dna import (
    AgentIdentity,
    AvailabilityStatus,
    CapabilityTag,
    Domain,
    ModelDependency,
)
from orchestration.agent_router import AgentRouter
from orchestration.brain_former import DynamicBrainFormer, brain_to_routing_decision
from orchestration.workflow_runner import WorkflowRunner


def _identity(agent_id: str, domain: Domain, proficiency: float = 0.7, availability=AvailabilityStatus.ONLINE) -> AgentIdentity:
    return AgentIdentity(
        id=agent_id, name=agent_id.title(), description="test agent",
        capabilities=[CapabilityTag(name=f"{domain.value}_capability", domain=domain, declared_proficiency=proficiency)],
        domains=[domain],
        model_dependency=ModelDependency(provider="none"),
        availability=availability,
    )


# ---------------------------------------------------------------------------
# Capability extraction
# ---------------------------------------------------------------------------


def test_extract_required_domains_matches_planning_phrases() -> None:
    domains = DynamicBrainFormer._extract_required_domains("Create a roadmap and steps", True, [])
    assert Domain.PLANNING in domains


def test_extract_required_domains_bundles_planning_and_review_for_research() -> None:
    domains = DynamicBrainFormer._extract_required_domains("Research and compare these options", True, [])
    assert domains == {Domain.PLANNING, Domain.RESEARCH, Domain.REVIEW}


def test_extract_required_domains_returns_empty_for_simple_message() -> None:
    domains = DynamicBrainFormer._extract_required_domains("Explain photosynthesis simply", True, [])
    assert domains == set()


def test_extract_required_domains_excludes_memory_when_disabled() -> None:
    domains = DynamicBrainFormer._extract_required_domains("Remember what we discussed earlier", False, [])
    assert Domain.MEMORY not in domains


def test_extract_required_domains_includes_memory_when_enabled_with_history() -> None:
    domains = DynamicBrainFormer._extract_required_domains("Remember what we discussed earlier", True, ["prior note"])
    assert Domain.MEMORY in domains


# ---------------------------------------------------------------------------
# Candidate discovery / scoring
# ---------------------------------------------------------------------------


def test_candidates_for_domain_excludes_offline_agents() -> None:
    reg = AgentRegistry()
    reg.register(_identity("offline-planner", Domain.PLANNING, availability=AvailabilityStatus.OFFLINE))
    former = DynamicBrainFormer(agent_registry=reg)
    assert former._candidates_for(Domain.PLANNING) == []


def test_candidates_for_domain_includes_standby_agents() -> None:
    """STANDBY means idle-but-ready, not unavailable — must be a valid candidate."""
    reg = AgentRegistry()
    reg.register(_identity("standby-critic", Domain.REVIEW, availability=AvailabilityStatus.STANDBY))
    former = DynamicBrainFormer(agent_registry=reg)
    candidates = former._candidates_for(Domain.REVIEW)
    assert [identity.id for identity in candidates] == ["standby-critic"]


def test_select_best_prefers_higher_declared_proficiency() -> None:
    reg = AgentRegistry()
    reg.register(_identity("weak", Domain.PLANNING, proficiency=0.3))
    reg.register(_identity("strong", Domain.PLANNING, proficiency=0.9))
    former = DynamicBrainFormer(agent_registry=reg)
    candidates = former._candidates_for(Domain.PLANNING)
    best = former._select_best(candidates, Domain.PLANNING)
    assert best.identity.id == "strong"


def test_select_best_uses_measured_success_rate_as_tiebreaker() -> None:
    reg = AgentRegistry()
    reg.register(_identity("no-history", Domain.PLANNING, proficiency=0.7))
    reg.register(_identity("proven", Domain.PLANNING, proficiency=0.7))
    reg.record_run("proven", success=True, confidence=None, latency_ms=1.0)
    former = DynamicBrainFormer(agent_registry=reg)
    candidates = former._candidates_for(Domain.PLANNING)
    best = former._select_best(candidates, Domain.PLANNING)
    assert best.identity.id == "proven"


def test_select_best_is_deterministic_for_equal_scores() -> None:
    """No proficiency or performance difference: agent id breaks the tie,
    and repeated calls must return the same result."""
    reg = AgentRegistry()
    reg.register(_identity("agent-a", Domain.PLANNING, proficiency=0.5))
    reg.register(_identity("agent-b", Domain.PLANNING, proficiency=0.5))
    former = DynamicBrainFormer(agent_registry=reg)
    candidates = former._candidates_for(Domain.PLANNING)
    results = {former._select_best(candidates, Domain.PLANNING).identity.id for _ in range(5)}
    assert len(results) == 1


# ---------------------------------------------------------------------------
# Brain formation — single/multi-agent, real registry
# ---------------------------------------------------------------------------


def test_form_single_agent_brain_for_planning_request() -> None:
    import agents  # noqa: F401 — ensures core agents are registered

    former = DynamicBrainFormer()
    brain = former.form(task_id="t1", message="Create a roadmap and steps for launch", mode="auto", selected_agents=[], available_memory=[], memory_enabled=True)

    assert brain.execution_order == ["planner"]
    assert brain.required_domains == [Domain.PLANNING]
    assert brain.used_fallback is False
    assert brain.selected_agents[0].matched_capability is not None
    assert brain.selected_agents[0].declared_proficiency is not None


def test_form_multi_agent_brain_for_research_request() -> None:
    import agents  # noqa: F401

    former = DynamicBrainFormer()
    brain = former.form(task_id="t2", message="Research and compare solar options", mode="auto", selected_agents=[], available_memory=[], memory_enabled=True)

    assert brain.execution_order == ["planner", "researcher", "critic"]
    assert set(brain.required_domains) == {Domain.PLANNING, Domain.RESEARCH, Domain.REVIEW}


def test_form_no_domains_returns_empty_brain_without_fallback() -> None:
    import agents  # noqa: F401

    former = DynamicBrainFormer()
    brain = former.form(task_id="t3", message="Explain photosynthesis simply", mode="auto", selected_agents=[], available_memory=[], memory_enabled=True)

    assert brain.execution_order == []
    assert brain.used_fallback is False


def test_form_manual_mode_bypasses_capability_inference() -> None:
    import agents  # noqa: F401

    former = DynamicBrainFormer()
    brain = former.form(task_id="t4", message="anything", mode="manual", selected_agents=["memory", "critic"], available_memory=[], memory_enabled=True)

    assert brain.execution_order == ["memory", "critic"]
    assert all(selection.domain is None for selection in brain.selected_agents)


def test_form_quick_mode_selects_no_agents() -> None:
    former = DynamicBrainFormer()
    brain = former.form(task_id="t5", message="Hello", mode="quick", selected_agents=[], available_memory=[], memory_enabled=True)
    assert brain.execution_order == []


def test_form_research_mode_uses_fixed_team() -> None:
    import agents  # noqa: F401

    former = DynamicBrainFormer()
    brain = former.form(task_id="t6", message="Study the market", mode="research", selected_agents=[], available_memory=[], memory_enabled=True)
    assert brain.execution_order == ["planner", "researcher", "critic"]


# ---------------------------------------------------------------------------
# Fallback behavior
# ---------------------------------------------------------------------------


def test_form_falls_back_to_legacy_router_when_no_candidates_available() -> None:
    """An empty registry cannot resolve any domain, so brain formation must
    fall back to the legacy AgentRouter rather than returning nothing."""
    empty_registry = AgentRegistry()
    former = DynamicBrainFormer(agent_registry=empty_registry, router=AgentRouter())

    brain = former.form(task_id="t7", message="Create a roadmap and steps", mode="auto", selected_agents=[], available_memory=[], memory_enabled=True)

    assert brain.used_fallback is True
    assert brain.fallback_reason is not None
    assert "planning" in brain.fallback_reason
    # Legacy router still recognizes the same keyword and would select "planner",
    # confirming fallback genuinely delegates rather than returning nothing.
    assert brain.execution_order == ["planner"]


def test_fallback_is_never_used_when_all_domains_are_resolvable() -> None:
    import agents  # noqa: F401

    former = DynamicBrainFormer()
    brain = former.form(task_id="t8", message="Research and compare solar options", mode="auto", selected_agents=[], available_memory=[], memory_enabled=True)
    assert brain.used_fallback is False
    assert brain.fallback_reason is None


# ---------------------------------------------------------------------------
# brain_to_routing_decision adapter
# ---------------------------------------------------------------------------


def test_brain_to_routing_decision_preserves_execution_order_and_reason() -> None:
    import agents  # noqa: F401

    former = DynamicBrainFormer()
    brain = former.form(task_id="t9", message="Create a roadmap and steps", mode="auto", selected_agents=[], available_memory=[], memory_enabled=True)
    decision = brain_to_routing_decision(brain)
    assert decision.execution_order == brain.execution_order
    assert decision.selected_agents == brain.execution_order
    assert decision.reason == brain.formation_reason


# ---------------------------------------------------------------------------
# End-to-end: brain formation executes through the Cognitive Bus, and is
# traceable in the task's message history.
# ---------------------------------------------------------------------------


def run_chat(request: ChatRequest, runner: WorkflowRunner | None = None):
    return asyncio.run((runner or WorkflowRunner()).run(request))


def test_brain_formation_is_traceable_via_cognitive_bus() -> None:
    runner = WorkflowRunner()
    response = run_chat(ChatRequest(message="Research and compare solar options"), runner)

    task_messages = runner.bus.get_task_messages(response.task_id)
    brain_events = [message for message in task_messages if message.intent == "brain_formed"]
    assert len(brain_events) == 1
    assert brain_events[0].target_agent is None  # broadcast, observable by any task-level subscriber
    assert brain_events[0].context["selected_agents"] == ["planner", "researcher", "critic"]
    assert brain_events[0].context["used_fallback"] is False


def test_brain_formed_event_precedes_agent_execution_messages() -> None:
    runner = WorkflowRunner()
    response = run_chat(ChatRequest(message="Create a roadmap and steps for launch"), runner)

    intents = [message.intent for message in runner.bus.get_task_messages(response.task_id)]
    assert intents[0] == "brain_formed"
    assert "execute" in intents


def test_task_isolation_holds_across_different_brains() -> None:
    """Two different requests on the same runner must not mix Brain trace
    messages — a direct regression guard on top of Phase B's bus isolation."""
    runner = WorkflowRunner()
    first = run_chat(ChatRequest(message="Create a roadmap and steps"), runner)
    second = run_chat(ChatRequest(message="Research and compare options"), runner)

    first_messages = runner.bus.get_task_messages(first.task_id)
    second_messages = runner.bus.get_task_messages(second.task_id)
    assert all(message.task_id == first.task_id for message in first_messages)
    assert all(message.task_id == second.task_id for message in second_messages)
