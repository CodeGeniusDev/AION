"""Tool Registry: discovery layer for the Tool System.

Structurally mirrors agents/registry.py's AgentRegistry — same idempotent
registration semantics, same find_by_capability query shape, same
performance-recording pattern — so Dynamic Brain Formation's existing
capability-matching approach for agents has a direct analogue for tools
rather than a second, differently-shaped discovery mechanism.
"""

from abc import ABC, abstractmethod

from models.cognitive_dna import AvailabilityStatus, Domain
from models.tool import ToolIdentity
from tools.base import BaseTool


class ToolIdentityMismatchError(ValueError):
    """Raised when a ToolIdentity.id does not match the tool instance's id."""


class DuplicateToolRegistrationError(ValueError):
    """Raised when a different tool identity attempts to register under an
    id that already holds a different-version identity."""


class UnknownToolError(KeyError):
    """Raised when an operation references a tool_id that was never registered."""


class ToolRegistryInterface(ABC):
    @abstractmethod
    def register(self, identity: ToolIdentity, tool: BaseTool | None = None) -> None: ...

    @abstractmethod
    def unregister(self, tool_id: str) -> None: ...

    @abstractmethod
    def get_identity(self, tool_id: str) -> ToolIdentity | None: ...

    @abstractmethod
    def get_tool(self, tool_id: str) -> BaseTool | None: ...

    @abstractmethod
    def list_identities(self) -> list[ToolIdentity]: ...

    @abstractmethod
    def find_by_capability(
        self, *, capability_name: str | None = None, domain: Domain | None = None,
        min_declared_proficiency: float = 0.0, available_only: bool = True,
    ) -> list[ToolIdentity]: ...

    @abstractmethod
    def record_run(self, tool_id: str, *, success: bool, latency_ms: float) -> None: ...

    @abstractmethod
    def clear(self) -> None: ...


class ToolRegistry(ToolRegistryInterface):
    def __init__(self) -> None:
        self._identities: dict[str, ToolIdentity] = {}
        self._instances: dict[str, BaseTool] = {}

    def register(self, identity: ToolIdentity, tool: BaseTool | None = None) -> None:
        if tool is not None and tool.id != identity.id:
            raise ToolIdentityMismatchError(
                f"ToolIdentity.id '{identity.id}' does not match tool.id '{tool.id}'"
            )
        existing = self._identities.get(identity.id)
        if existing is not None:
            if existing.version == identity.version:
                if tool is not None:
                    self._instances[identity.id] = tool
                return  # idempotent: same id/version re-registering
            raise DuplicateToolRegistrationError(
                f"Tool id '{identity.id}' is already registered at version "
                f"'{existing.version}'; refusing to silently replace it with version '{identity.version}'."
            )
        self._identities[identity.id] = identity
        if tool is not None:
            self._instances[identity.id] = tool

    def unregister(self, tool_id: str) -> None:
        self._identities.pop(tool_id, None)
        self._instances.pop(tool_id, None)

    def get_identity(self, tool_id: str) -> ToolIdentity | None:
        return self._identities.get(tool_id)

    def get_tool(self, tool_id: str) -> BaseTool | None:
        return self._instances.get(tool_id)

    def list_identities(self) -> list[ToolIdentity]:
        return list(self._identities.values())

    def find_by_capability(
        self, *, capability_name: str | None = None, domain: Domain | None = None,
        min_declared_proficiency: float = 0.0, available_only: bool = True,
    ) -> list[ToolIdentity]:
        results = []
        for identity in self._identities.values():
            if available_only and identity.availability not in (AvailabilityStatus.ONLINE, AvailabilityStatus.DEGRADED):
                continue
            matching = [
                capability for capability in identity.capabilities
                if (capability_name is None or capability.name == capability_name)
                and (domain is None or capability.domain == domain)
                and capability.declared_proficiency >= min_declared_proficiency
            ]
            if matching:
                results.append(identity)
        return results

    def record_run(self, tool_id: str, *, success: bool, latency_ms: float) -> None:
        identity = self._identities.get(tool_id)
        if identity is None:
            raise UnknownToolError(tool_id)
        performance = identity.performance
        performance.total_runs += 1
        if success:
            performance.successful_runs += 1
        else:
            performance.failed_runs += 1
        performance.average_latency_ms = (
            latency_ms if performance.average_latency_ms is None
            else performance.average_latency_ms + (latency_ms - performance.average_latency_ms) / performance.total_runs
        )
        from datetime import datetime, timezone
        performance.last_run_at = datetime.now(timezone.utc)

    def clear(self) -> None:
        self._identities.clear()
        self._instances.clear()


# Process-wide default registry, mirroring agents.registry.registry.
registry = ToolRegistry()
