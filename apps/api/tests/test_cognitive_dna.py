"""Tests for Cognitive DNA (models/cognitive_dna.py) and the Agent Registry
(agents/registry.py). Covers schema validation, registration, duplicate
protection, capability discovery, availability filtering, performance
recording, invariants, and import-time idempotency.

Unit tests below construct a fresh, isolated AgentRegistry() for anything
that doesn't need the real four agents, so they cannot interfere with the
global `registry` singleton (which the `_isolate_agent_registry` fixture in
conftest.py additionally snapshots/restores around every test).
"""

import pytest
from pydantic import ValidationError

from agents.base import BaseAgent
from agents.registry import (
    AgentRegistry,
    DuplicateRegistrationError,
    IdentityMismatchError,
    UnknownAgentError,
)
from models.cognitive_dna import (
    AgentIdentity,
    AvailabilityStatus,
    CapabilityTag,
    Domain,
    ModelDependency,
)


def _make_identity(
    agent_id: str = "test-agent",
    version: str = "1.0.0",
    capability_name: str = "sample_capability",
    domain: Domain = Domain.GENERAL,
    declared_proficiency: float = 0.5,
    availability: AvailabilityStatus = AvailabilityStatus.ONLINE,
) -> AgentIdentity:
    return AgentIdentity(
        id=agent_id,
        name="Test Agent",
        version=version,
        description="An agent used only for registry tests.",
        capabilities=[
            CapabilityTag(name=capability_name, domain=domain, declared_proficiency=declared_proficiency)
        ],
        domains=[domain],
        model_dependency=ModelDependency(provider="none", required=False),
        availability=availability,
    )


class _DummyAgent(BaseAgent):
    id = "test-agent"
    name = "Test Agent"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_capability_tag_rejects_proficiency_outside_unit_interval() -> None:
    with pytest.raises(ValidationError):
        CapabilityTag(name="x", domain=Domain.GENERAL, declared_proficiency=1.5)
    with pytest.raises(ValidationError):
        CapabilityTag(name="x", domain=Domain.GENERAL, declared_proficiency=-0.1)


def test_agent_identity_requires_at_least_one_capability() -> None:
    with pytest.raises(ValidationError):
        AgentIdentity(
            id="a", name="A", description="d",
            capabilities=[],
            domains=[Domain.GENERAL],
            model_dependency=ModelDependency(provider="none"),
        )


def test_agent_identity_requires_at_least_one_domain() -> None:
    with pytest.raises(ValidationError):
        AgentIdentity(
            id="a", name="A", description="d",
            capabilities=[CapabilityTag(name="x", domain=Domain.GENERAL)],
            domains=[],
            model_dependency=ModelDependency(provider="none"),
        )


def test_performance_history_starts_empty_with_no_invented_values() -> None:
    identity = _make_identity()
    assert identity.performance.total_runs == 0
    assert identity.performance.successful_runs == 0
    assert identity.performance.failed_runs == 0
    assert identity.performance.average_confidence is None
    assert identity.performance.average_latency_ms is None
    assert identity.performance.last_run_at is None
    assert identity.performance.success_rate is None


def test_capability_declared_proficiency_is_distinct_from_measured_performance() -> None:
    """declared_proficiency (design-time prior) and PerformanceHistory
    (measured record) must be independently settable — the schema must not
    conflate the two."""
    identity = _make_identity(declared_proficiency=0.9)
    assert identity.capabilities[0].declared_proficiency == 0.9
    assert identity.performance.success_rate is None  # nothing measured yet


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_and_retrieve_identity() -> None:
    reg = AgentRegistry()
    identity = _make_identity()
    reg.register(identity, _DummyAgent())
    assert reg.get_identity("test-agent") == identity
    assert isinstance(reg.get_agent("test-agent"), _DummyAgent)


def test_register_without_agent_instance_is_allowed() -> None:
    """Identity registration must not require an agent instance — this is
    what makes future external/third-party agent registration possible
    without requiring a BaseAgent subclass."""
    reg = AgentRegistry()
    identity = _make_identity()
    reg.register(identity)
    assert reg.get_identity("test-agent") == identity
    assert reg.get_agent("test-agent") is None


def test_register_rejects_identity_agent_id_mismatch() -> None:
    reg = AgentRegistry()
    identity = _make_identity(agent_id="mismatched-id")

    class _OtherAgent(BaseAgent):
        id = "different-id"

    with pytest.raises(IdentityMismatchError):
        reg.register(identity, _OtherAgent())


def test_register_same_id_and_version_twice_is_idempotent_noop() -> None:
    """Guards against duplicate global registration when an agent module is
    imported more than once (e.g. across test files)."""
    reg = AgentRegistry()
    identity = _make_identity()
    reg.register(identity, _DummyAgent())
    reg.register(identity, _DummyAgent())  # should not raise
    assert len(reg.list_identities()) == 1


def test_register_conflicting_version_for_same_id_raises() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity(version="1.0.0"))
    with pytest.raises(DuplicateRegistrationError):
        reg.register(_make_identity(version="2.0.0"))


def test_idempotent_reregistration_preserves_existing_performance_history() -> None:
    reg = AgentRegistry()
    identity = _make_identity()
    reg.register(identity)
    reg.record_run("test-agent", success=True, confidence=0.9, latency_ms=120.0)

    reg.register(identity)  # re-register same id/version

    assert reg.get_identity("test-agent").performance.total_runs == 1


def test_unregister_removes_identity_and_instance() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity(), _DummyAgent())
    reg.unregister("test-agent")
    assert reg.get_identity("test-agent") is None
    assert reg.get_agent("test-agent") is None


def test_clear_removes_all_registrations() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity(agent_id="a"))
    reg.register(_make_identity(agent_id="b"))
    reg.clear()
    assert reg.list_identities() == []


# ---------------------------------------------------------------------------
# Capability discovery
# ---------------------------------------------------------------------------


def test_find_by_capability_matches_by_name() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity(agent_id="a", capability_name="alpha"))
    reg.register(_make_identity(agent_id="b", capability_name="beta"))
    results = reg.find_by_capability(capability_name="alpha")
    assert [identity.id for identity in results] == ["a"]


def test_find_by_capability_filters_by_domain() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity(agent_id="planner-like", domain=Domain.PLANNING))
    reg.register(_make_identity(agent_id="research-like", domain=Domain.RESEARCH))
    results = reg.find_by_capability(domain=Domain.RESEARCH)
    assert [identity.id for identity in results] == ["research-like"]


def test_find_by_capability_filters_by_min_declared_proficiency() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity(agent_id="weak", declared_proficiency=0.2))
    reg.register(_make_identity(agent_id="strong", declared_proficiency=0.9))
    results = reg.find_by_capability(min_declared_proficiency=0.5)
    assert [identity.id for identity in results] == ["strong"]


def test_find_by_capability_available_only_excludes_offline_agents() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity(agent_id="offline-one", availability=AvailabilityStatus.OFFLINE))
    reg.register(_make_identity(agent_id="online-one", availability=AvailabilityStatus.ONLINE))
    results = reg.find_by_capability(available_only=True)
    assert [identity.id for identity in results] == ["online-one"]


def test_find_by_capability_available_only_false_includes_offline_agents() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity(agent_id="offline-one", availability=AvailabilityStatus.OFFLINE))
    results = reg.find_by_capability(available_only=False)
    assert [identity.id for identity in results] == ["offline-one"]


def test_find_by_capability_treats_degraded_as_available() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity(agent_id="degraded-one", availability=AvailabilityStatus.DEGRADED))
    results = reg.find_by_capability(available_only=True)
    assert [identity.id for identity in results] == ["degraded-one"]


def test_find_by_capability_returns_empty_list_when_nothing_matches() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity())
    assert reg.find_by_capability(capability_name="does-not-exist") == []


# ---------------------------------------------------------------------------
# Performance recording
# ---------------------------------------------------------------------------


def test_record_run_updates_success_and_failure_counts() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity())
    reg.record_run("test-agent", success=True, confidence=0.8, latency_ms=100.0)
    reg.record_run("test-agent", success=False, confidence=None, latency_ms=50.0)
    performance = reg.get_identity("test-agent").performance
    assert performance.total_runs == 2
    assert performance.successful_runs == 1
    assert performance.failed_runs == 1


def test_record_run_computes_success_rate() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity())
    reg.record_run("test-agent", success=True, confidence=None, latency_ms=10.0)
    reg.record_run("test-agent", success=True, confidence=None, latency_ms=10.0)
    reg.record_run("test-agent", success=False, confidence=None, latency_ms=10.0)
    assert reg.get_identity("test-agent").performance.success_rate == pytest.approx(2 / 3)


def test_record_run_computes_running_average_latency() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity())
    reg.record_run("test-agent", success=True, confidence=None, latency_ms=100.0)
    reg.record_run("test-agent", success=True, confidence=None, latency_ms=200.0)
    assert reg.get_identity("test-agent").performance.average_latency_ms == pytest.approx(150.0)


def test_record_run_ignores_confidence_when_none() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity())
    reg.record_run("test-agent", success=True, confidence=None, latency_ms=10.0)
    assert reg.get_identity("test-agent").performance.average_confidence is None


def test_record_run_averages_confidence_when_provided() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity())
    reg.record_run("test-agent", success=True, confidence=0.6, latency_ms=10.0)
    reg.record_run("test-agent", success=True, confidence=0.8, latency_ms=10.0)
    assert reg.get_identity("test-agent").performance.average_confidence == pytest.approx(0.7)


def test_record_run_unknown_agent_raises() -> None:
    reg = AgentRegistry()
    with pytest.raises(UnknownAgentError):
        reg.record_run("does-not-exist", success=True, confidence=None, latency_ms=1.0)


def test_performance_history_invariant_always_holds_after_record_run() -> None:
    reg = AgentRegistry()
    reg.register(_make_identity())
    for _ in range(5):
        reg.record_run("test-agent", success=True, confidence=None, latency_ms=1.0)
    performance = reg.get_identity("test-agent").performance
    assert performance.is_consistent()
    assert performance.successful_runs + performance.failed_runs == performance.total_runs


# ---------------------------------------------------------------------------
# Import-time registration of the real four agents
# ---------------------------------------------------------------------------


def test_all_four_core_agents_registered_at_import() -> None:
    import agents  # noqa: F401 — triggers registration side effects
    from agents.registry import registry as global_registry

    ids = {identity.id for identity in global_registry.list_identities()}
    assert {"planner", "researcher", "critic", "memory"}.issubset(ids)


def test_core_agent_identities_declare_at_least_one_capability_each() -> None:
    import agents  # noqa: F401
    from agents.registry import registry as global_registry

    for agent_id in ("planner", "researcher", "critic", "memory"):
        identity = global_registry.get_identity(agent_id)
        assert identity is not None
        assert len(identity.capabilities) >= 1


def test_reimporting_agents_module_does_not_raise_or_duplicate() -> None:
    """Guards against duplicate global registration errors if the agents
    package is imported more than once in the same process."""
    import importlib

    import agents
    from agents.registry import registry as global_registry

    before = len(global_registry.list_identities())
    importlib.reload(agents.planner)  # re-runs the module body, including registry.register(...)
    after = len(global_registry.list_identities())
    assert after == before


def test_core_agents_are_discoverable_by_domain() -> None:
    import agents  # noqa: F401
    from agents.registry import registry as global_registry

    planning_agents = global_registry.find_by_capability(domain=Domain.PLANNING)
    assert any(identity.id == "planner" for identity in planning_agents)

    # CriticAgent is declared STANDBY (matches its existing `status` value),
    # so it is correctly excluded by the default available_only=True filter;
    # querying with available_only=False confirms it is still discoverable.
    review_agents = global_registry.find_by_capability(domain=Domain.REVIEW, available_only=False)
    assert any(identity.id == "critic" for identity in review_agents)


def test_critic_agent_declared_availability_matches_existing_status() -> None:
    """Backward-compatibility check: CriticAgent.status == 'standby' in the
    existing code, so its Cognitive DNA availability must match."""
    import agents  # noqa: F401
    from agents.registry import registry as global_registry

    identity = global_registry.get_identity("critic")
    assert identity.availability == AvailabilityStatus.STANDBY
