"""Agent Registry: the discovery layer over Cognitive DNA.

This is infrastructure, not intelligence. `AgentRegistry` does not decide
which agent is best for a task — it answers structural queries ("which
registered identities declare this capability/domain and are available?").
The judgment of what to do with that answer belongs to Dynamic Brain
Formation (Phase C) and later phases. Treat this module as a lookup table
with light validation, not a reasoning component.

Replaceability: `AgentRegistryInterface` is an abstract contract. The
in-memory `AgentRegistry` below is the Phase A implementation. A later phase
could implement the same interface backed by a database or a distributed
store without any caller (router, workflow runner, future brain former)
needing to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from agents.base import BaseAgent
from models.cognitive_dna import AgentIdentity, AvailabilityStatus, Domain


class IdentityMismatchError(ValueError):
    """Raised when an AgentIdentity.id does not match the agent instance's id."""


class DuplicateRegistrationError(ValueError):
    """Raised when a different identity attempts to register under an id
    that already holds a different-version identity — a genuine conflict,
    as opposed to the same id/version registering twice (idempotent no-op)."""


class UnknownAgentError(KeyError):
    """Raised when an operation references an agent_id that was never registered."""


class AgentRegistryInterface(ABC):
    """Abstract contract for agent discovery. Implement this to back the
    registry with persistent or distributed storage later; every caller in
    AION depends on this interface, not on the in-memory implementation."""

    @abstractmethod
    def register(self, identity: AgentIdentity, agent: BaseAgent | None = None) -> None: ...

    @abstractmethod
    def unregister(self, agent_id: str) -> None: ...

    @abstractmethod
    def get_identity(self, agent_id: str) -> AgentIdentity | None: ...

    @abstractmethod
    def get_agent(self, agent_id: str) -> BaseAgent | None: ...

    @abstractmethod
    def list_identities(self) -> list[AgentIdentity]: ...

    @abstractmethod
    def find_by_capability(
        self,
        *,
        capability_name: str | None = None,
        domain: Domain | None = None,
        min_declared_proficiency: float = 0.0,
        available_only: bool = True,
    ) -> list[AgentIdentity]: ...

    @abstractmethod
    def record_run(
        self,
        agent_id: str,
        *,
        success: bool,
        confidence: float | None,
        latency_ms: float,
    ) -> None: ...

    @abstractmethod
    def clear(self) -> None:
        """Remove all registrations. For test isolation / administrative
        reset only — never called during normal request handling."""


class AgentRegistry(AgentRegistryInterface):
    """In-memory implementation. Process-lifetime storage, no persistence.

    Registration is idempotent for the common case (module re-import
    registering the same id + version again is a silent no-op, so agent
    modules can be safely imported more than once without error or data
    loss). A genuine conflict — the same id registering under a *different*
    version while the old version is still present — raises
    `DuplicateRegistrationError` rather than silently overwriting
    performance history that may already exist for that id.
    """

    def __init__(self) -> None:
        self._identities: dict[str, AgentIdentity] = {}
        self._instances: dict[str, BaseAgent] = {}

    def register(self, identity: AgentIdentity, agent: BaseAgent | None = None) -> None:
        if agent is not None and agent.id != identity.id:
            raise IdentityMismatchError(
                f"AgentIdentity.id '{identity.id}' does not match agent.id '{agent.id}'"
            )

        existing = self._identities.get(identity.id)
        if existing is not None:
            if existing.version == identity.version:
                # Same agent, same version, registering again (e.g. duplicate
                # import during tests): no-op, preserve existing performance history.
                if agent is not None:
                    self._instances[identity.id] = agent
                return
            raise DuplicateRegistrationError(
                f"Agent id '{identity.id}' is already registered at version "
                f"'{existing.version}'; refusing to silently replace it with "
                f"version '{identity.version}'. Unregister the old version first "
                f"if this is an intentional upgrade."
            )

        self._identities[identity.id] = identity
        if agent is not None:
            self._instances[identity.id] = agent

    def unregister(self, agent_id: str) -> None:
        self._identities.pop(agent_id, None)
        self._instances.pop(agent_id, None)

    def get_identity(self, agent_id: str) -> AgentIdentity | None:
        return self._identities.get(agent_id)

    def get_agent(self, agent_id: str) -> BaseAgent | None:
        return self._instances.get(agent_id)

    def list_identities(self) -> list[AgentIdentity]:
        return list(self._identities.values())

    def find_by_capability(
        self,
        *,
        capability_name: str | None = None,
        domain: Domain | None = None,
        min_declared_proficiency: float = 0.0,
        available_only: bool = True,
    ) -> list[AgentIdentity]:
        results = []
        for identity in self._identities.values():
            if available_only and identity.availability not in (
                AvailabilityStatus.ONLINE,
                AvailabilityStatus.DEGRADED,
            ):
                continue
            matching_capabilities = [
                capability
                for capability in identity.capabilities
                if (capability_name is None or capability.name == capability_name)
                and (domain is None or capability.domain == domain)
                and capability.declared_proficiency >= min_declared_proficiency
            ]
            if matching_capabilities:
                results.append(identity)
        return results

    def record_run(
        self,
        agent_id: str,
        *,
        success: bool,
        confidence: float | None,
        latency_ms: float,
    ) -> None:
        identity = self._identities.get(agent_id)
        if identity is None:
            raise UnknownAgentError(agent_id)

        performance = identity.performance
        performance.total_runs += 1
        if success:
            performance.successful_runs += 1
        else:
            performance.failed_runs += 1

        if confidence is not None:
            performance.average_confidence = (
                confidence
                if performance.average_confidence is None
                else _running_average(performance.average_confidence, confidence, performance.total_runs)
            )
        performance.average_latency_ms = (
            latency_ms
            if performance.average_latency_ms is None
            else _running_average(performance.average_latency_ms, latency_ms, performance.total_runs)
        )
        performance.last_run_at = datetime.now(timezone.utc)

        if not performance.is_consistent():
            # Defensive: should be unreachable given the increments above,
            # but never leave the record in a state that violates its own invariant.
            raise AssertionError(f"PerformanceHistory invariant violated for '{agent_id}'")

    def clear(self) -> None:
        self._identities.clear()
        self._instances.clear()


def _running_average(current_average: float, new_value: float, count: int) -> float:
    return current_average + (new_value - current_average) / count


# Process-wide default registry. Agent modules register themselves here at
# import time. A future persistent/distributed implementation would be
# constructed and used the same way, satisfying `AgentRegistryInterface`.
registry = AgentRegistry()
