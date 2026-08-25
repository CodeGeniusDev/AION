"""Tool execution: timeout enforcement, error isolation, and telemetry.

A tool exception or timeout NEVER propagates out of `execute()` — it always
returns a ToolOutput(success=False, error=...) instead, and always records
real telemetry via the registry (success/failure counts are measured, never
invented). This mirrors WorkflowRunner's own fail-safe pattern for agent
execution and immune evaluation.
"""

import asyncio
from time import perf_counter
from typing import Any

from models.tool import ToolOutput
from tools.registry import ToolRegistryInterface
from tools.registry import registry as default_registry


class ToolExecutor:
    def __init__(self, tool_registry: ToolRegistryInterface | None = None) -> None:
        self.registry = tool_registry or default_registry

    async def execute(self, tool_id: str, *, task_id: str, parameters: dict[str, Any]) -> ToolOutput:
        identity = self.registry.get_identity(tool_id)
        tool = self.registry.get_tool(tool_id)
        if identity is None or tool is None:
            return ToolOutput(tool_id=tool_id, task_id=task_id, success=False, error=f"Unknown tool '{tool_id}'")

        started = perf_counter()
        try:
            output = await asyncio.wait_for(tool.execute(task_id, parameters), timeout=identity.timeout_seconds)
            latency_ms = (perf_counter() - started) * 1000
            output.latency_ms = latency_ms
            self.registry.record_run(tool_id, success=output.success, latency_ms=latency_ms)
            return output
        except asyncio.TimeoutError:
            latency_ms = (perf_counter() - started) * 1000
            self.registry.record_run(tool_id, success=False, latency_ms=latency_ms)
            return ToolOutput(
                tool_id=tool_id, task_id=task_id, success=False,
                error=f"Tool '{tool_id}' timed out after {identity.timeout_seconds}s", latency_ms=latency_ms,
            )
        except Exception as exc:  # must never propagate — isolation is the point
            latency_ms = (perf_counter() - started) * 1000
            self.registry.record_run(tool_id, success=False, latency_ms=latency_ms)
            return ToolOutput(tool_id=tool_id, task_id=task_id, success=False, error=str(exc), latency_ms=latency_ms)
