"""Tool schemas: declarative tool identity, compatible with Cognitive DNA.

`ToolIdentity` deliberately reuses `CapabilityTag`, `Domain`, and
`PerformanceHistory` from models/cognitive_dna.py rather than defining a
parallel set of concepts — a tool's capabilities are described the same way
an agent's are, so Dynamic Brain Formation's existing discovery pattern
(AgentRegistry.find_by_capability) has a direct structural analogue for
tools (ToolRegistry.find_by_capability, see tools/registry.py) instead of a
second, incompatible vocabulary.

`PerformanceHistory` is real and measured the same way it is for agents:
empty until ToolRegistry.record_run() is called from an actual execution.
Nothing here is pre-populated with invented numbers.
"""

from pydantic import BaseModel, Field

from models.cognitive_dna import AvailabilityStatus, CapabilityTag, Domain, PerformanceHistory


class ToolIdentity(BaseModel):
    id: str
    name: str
    description: str
    capabilities: list[CapabilityTag] = Field(min_length=1)
    domains: list[Domain] = Field(min_length=1)
    timeout_seconds: float = Field(default=5.0, gt=0.0)
    # Whether output from this tool must pass Immune System verification
    # before being memory-eligible. True for every current tool — even a
    # deterministic, correctly-implemented tool's output isn't automatically
    # "verified" in the Immune System's sense, which is about corroboration
    # against other evidence, not computational correctness. See
    # tools/executor.py / orchestration/workflow_runner.py for where this
    # is enforced.
    requires_verification: bool = True
    version: str = "1.0.0"
    provenance: str = "aion-core"
    availability: AvailabilityStatus = AvailabilityStatus.ONLINE
    performance: PerformanceHistory = Field(default_factory=PerformanceHistory)


class ToolOutput(BaseModel):
    tool_id: str
    task_id: str
    success: bool
    content: str = ""
    data: dict[str, object] = Field(default_factory=dict)
    error: str | None = None
    latency_ms: float = 0.0
