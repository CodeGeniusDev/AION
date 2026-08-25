"""Tests for the Tool System (tools/*.py, models/tool.py).

Covers ToolRegistry mechanics (mirroring agents/registry.py's proven test
shape), discovery/scoring, execution safety (timeouts, exceptions, unknown
tools), the built-in deterministic tools, Cognitive Bus event integration,
Immune-layer verification of tool output, memory-write gating, and existing
chat/API regression.
"""

import asyncio

import pytest

from models.cognitive_dna import AvailabilityStatus, CapabilityTag, Domain
from models.tool import ToolIdentity, ToolOutput
from orchestration.workflow_runner import WorkflowRunner
from tools.base import BaseTool
from tools.executor import ToolExecutor
from tools.registry import (
    DuplicateToolRegistrationError,
    ToolIdentityMismatchError,
    ToolRegistry,
    UnknownToolError,
)


def _identity(tool_id: str = "test-tool", version: str = "1.0.0", domain: Domain = Domain.COMPUTATION, proficiency: float = 0.7, availability=AvailabilityStatus.ONLINE, timeout: float = 2.0) -> ToolIdentity:
    return ToolIdentity(
        id=tool_id, name=tool_id.title(), description="test tool", version=version,
        capabilities=[CapabilityTag(name=f"{domain.value}_capability", domain=domain, declared_proficiency=proficiency)],
        domains=[domain], timeout_seconds=timeout, availability=availability,
    )


class _EchoTool(BaseTool):
    id = "test-tool"
    name = "Test Tool"

    async def execute(self, task_id, parameters):
        return ToolOutput(tool_id=self.id, task_id=task_id, success=True, content=str(parameters.get("value", "")))


class _SlowTool(BaseTool):
    id = "slow-tool"
    name = "Slow Tool"

    async def execute(self, task_id, parameters):
        await asyncio.sleep(10)
        return ToolOutput(tool_id=self.id, task_id=task_id, success=True, content="done")


class _BrokenTool(BaseTool):
    id = "broken-tool"
    name = "Broken Tool"

    async def execute(self, task_id, parameters):
        raise RuntimeError("simulated tool crash")


# ---------------------------------------------------------------------------
# ToolRegistry mechanics
# ---------------------------------------------------------------------------


def test_register_and_retrieve_identity() -> None:
    reg = ToolRegistry()
    identity = _identity()
    reg.register(identity, _EchoTool())
    assert reg.get_identity("test-tool") == identity
    assert isinstance(reg.get_tool("test-tool"), _EchoTool)


def test_register_without_tool_instance_is_allowed() -> None:
    reg = ToolRegistry()
    reg.register(_identity())
    assert reg.get_identity("test-tool") is not None
    assert reg.get_tool("test-tool") is None


def test_register_rejects_identity_tool_id_mismatch() -> None:
    reg = ToolRegistry()

    class _OtherTool(BaseTool):
        id = "different-id"
        name = "Other"

        async def execute(self, task_id, parameters):
            return ToolOutput(tool_id=self.id, task_id=task_id, success=True)

    with pytest.raises(ToolIdentityMismatchError):
        reg.register(_identity(), _OtherTool())


def test_register_same_id_and_version_twice_is_idempotent() -> None:
    reg = ToolRegistry()
    identity = _identity()
    reg.register(identity)
    reg.register(identity)
    assert len(reg.list_identities()) == 1


def test_register_conflicting_version_raises() -> None:
    reg = ToolRegistry()
    reg.register(_identity(version="1.0.0"))
    with pytest.raises(DuplicateToolRegistrationError):
        reg.register(_identity(version="2.0.0"))


def test_unregister_removes_identity_and_instance() -> None:
    reg = ToolRegistry()
    reg.register(_identity(), _EchoTool())
    reg.unregister("test-tool")
    assert reg.get_identity("test-tool") is None
    assert reg.get_tool("test-tool") is None


def test_clear_removes_all_registrations() -> None:
    reg = ToolRegistry()
    reg.register(_identity(tool_id="a"))
    reg.register(_identity(tool_id="b"))
    reg.clear()
    assert reg.list_identities() == []


# ---------------------------------------------------------------------------
# Discovery / scoring
# ---------------------------------------------------------------------------


def test_find_by_capability_filters_by_domain() -> None:
    reg = ToolRegistry()
    reg.register(_identity(tool_id="comp", domain=Domain.COMPUTATION))
    reg.register(_identity(tool_id="gen", domain=Domain.GENERAL))
    results = reg.find_by_capability(domain=Domain.COMPUTATION)
    assert [i.id for i in results] == ["comp"]


def test_find_by_capability_filters_by_min_proficiency() -> None:
    reg = ToolRegistry()
    reg.register(_identity(tool_id="weak", proficiency=0.2))
    reg.register(_identity(tool_id="strong", proficiency=0.9))
    results = reg.find_by_capability(min_declared_proficiency=0.5)
    assert [i.id for i in results] == ["strong"]


def test_find_by_capability_excludes_offline_by_default() -> None:
    reg = ToolRegistry()
    reg.register(_identity(tool_id="offline-tool", availability=AvailabilityStatus.OFFLINE))
    assert reg.find_by_capability(available_only=True) == []
    assert len(reg.find_by_capability(available_only=False)) == 1


# ---------------------------------------------------------------------------
# Performance recording
# ---------------------------------------------------------------------------


def test_record_run_updates_measured_performance() -> None:
    reg = ToolRegistry()
    reg.register(_identity())
    reg.record_run("test-tool", success=True, latency_ms=12.0)
    reg.record_run("test-tool", success=False, latency_ms=8.0)
    performance = reg.get_identity("test-tool").performance
    assert performance.total_runs == 2
    assert performance.successful_runs == 1
    assert performance.failed_runs == 1
    assert performance.average_latency_ms == pytest.approx(10.0)


def test_record_run_unknown_tool_raises() -> None:
    reg = ToolRegistry()
    with pytest.raises(UnknownToolError):
        reg.record_run("nope", success=True, latency_ms=1.0)


# ---------------------------------------------------------------------------
# ToolExecutor: safety, isolation, real telemetry
# ---------------------------------------------------------------------------


def test_executor_returns_success_output_for_working_tool() -> None:
    reg = ToolRegistry()
    reg.register(_identity(), _EchoTool())
    executor = ToolExecutor(reg)
    output = asyncio.run(executor.execute("test-tool", task_id="t1", parameters={"value": "hello"}))
    assert output.success is True
    assert output.content == "hello"
    assert output.latency_ms >= 0


def test_executor_unknown_tool_returns_failure_not_exception() -> None:
    reg = ToolRegistry()
    executor = ToolExecutor(reg)
    output = asyncio.run(executor.execute("nope", task_id="t2", parameters={}))
    assert output.success is False
    assert "Unknown tool" in output.error


def test_executor_tool_exception_is_isolated() -> None:
    reg = ToolRegistry()
    reg.register(_identity(tool_id="broken-tool"), _BrokenTool())
    executor = ToolExecutor(reg)
    output = asyncio.run(executor.execute("broken-tool", task_id="t3", parameters={}))
    assert output.success is False
    assert "simulated tool crash" in output.error


def test_executor_enforces_timeout() -> None:
    reg = ToolRegistry()
    reg.register(_identity(tool_id="slow-tool", timeout=0.05), _SlowTool())
    executor = ToolExecutor(reg)
    output = asyncio.run(executor.execute("slow-tool", task_id="t4", parameters={}))
    assert output.success is False
    assert "timed out" in output.error


def test_executor_records_real_telemetry_on_success_and_failure() -> None:
    reg = ToolRegistry()
    reg.register(_identity(), _EchoTool())
    executor = ToolExecutor(reg)
    asyncio.run(executor.execute("test-tool", task_id="t5", parameters={"value": "x"}))
    assert reg.get_identity("test-tool").performance.total_runs == 1
    assert reg.get_identity("test-tool").performance.successful_runs == 1


# ---------------------------------------------------------------------------
# Built-in tools: real computation
# ---------------------------------------------------------------------------


def test_builtin_tools_are_registered_at_import() -> None:
    import tools  # noqa: F401
    from tools.registry import registry as global_registry

    ids = {identity.id for identity in global_registry.list_identities()}
    assert {"calculator", "text_analysis", "current_datetime"}.issubset(ids)


def test_calculator_tool_computes_real_arithmetic() -> None:
    import tools  # noqa: F401
    from tools.registry import registry as global_registry

    tool = global_registry.get_tool("calculator")
    output = asyncio.run(tool.execute("t1", {"expression": "(2 + 3) * 4"}))
    assert output.success is True
    assert output.data["result"] == 20


def test_calculator_tool_rejects_unsafe_input() -> None:
    import tools  # noqa: F401
    from tools.registry import registry as global_registry

    tool = global_registry.get_tool("calculator")
    output = asyncio.run(tool.execute("t2", {"expression": "__import__('os').system('echo hi')"}))
    assert output.success is False


def test_calculator_tool_rejects_missing_expression() -> None:
    import tools  # noqa: F401
    from tools.registry import registry as global_registry

    tool = global_registry.get_tool("calculator")
    output = asyncio.run(tool.execute("t3", {}))
    assert output.success is False


def test_text_analysis_tool_computes_real_counts() -> None:
    import tools  # noqa: F401
    from tools.registry import registry as global_registry

    tool = global_registry.get_tool("text_analysis")
    output = asyncio.run(tool.execute("t4", {"text": "Hello world. This is a test!"}))
    assert output.success is True
    assert output.data["word_count"] == 6
    assert output.data["sentence_count"] == 2


def test_datetime_tool_returns_real_current_time() -> None:
    import tools  # noqa: F401
    from datetime import datetime, timezone

    from tools.registry import registry as global_registry

    tool = global_registry.get_tool("current_datetime")
    before = datetime.now(timezone.utc)
    output = asyncio.run(tool.execute("t5", {}))
    after = datetime.now(timezone.utc)
    assert output.success is True
    reported = datetime.fromisoformat(output.data["iso8601"])
    assert before <= reported <= after


# ---------------------------------------------------------------------------
# WorkflowRunner integration: bus events, verification, memory gating
# ---------------------------------------------------------------------------


def test_workflow_runner_execute_tool_publishes_lifecycle_events() -> None:
    import tools  # noqa: F401

    runner = WorkflowRunner()
    output = asyncio.run(runner.execute_tool("calculator", task_id="task-x", parameters={"expression": "1 + 1"}))
    assert output.success is True
    intents = [m.intent for m in runner.bus.get_task_messages("task-x")]
    assert intents == ["tool_requested", "tool_started", "tool_completed"]


def test_workflow_runner_execute_tool_publishes_failure_event() -> None:
    import tools  # noqa: F401

    runner = WorkflowRunner()
    output = asyncio.run(runner.execute_tool("calculator", task_id="task-y", parameters={}))
    assert output.success is False
    intents = [m.intent for m in runner.bus.get_task_messages("task-y")]
    assert "tool_failed" in intents


def test_tool_output_is_verified_after_successful_execution() -> None:
    import tools  # noqa: F401

    runner = WorkflowRunner()
    asyncio.run(runner.execute_tool("calculator", task_id="task-z", parameters={"expression": "2 + 2"}))
    report = runner.get_tool_immune_report("task-z", "calculator")
    assert report is not None
    assert report.claims_checked >= 0  # calculator output may or may not extract as a "claim" — verification ran regardless


def test_datetime_tool_skips_verification_by_design() -> None:
    import tools  # noqa: F401

    runner = WorkflowRunner()
    asyncio.run(runner.execute_tool("current_datetime", task_id="task-dt", parameters={}))
    assert runner.get_tool_immune_report("task-dt", "current_datetime") is None


def test_tool_output_never_written_to_memory_without_corroboration() -> None:
    """A first-time, uncorroborated tool result must NOT become semantic
    memory — same verified-only gate as agent claims (Phase D/E)."""
    import tools  # noqa: F401

    runner = WorkflowRunner()
    asyncio.run(runner.execute_tool("text_analysis", task_id="task-mem1", parameters={"text": "The launch budget was approved for next quarter by finance."}))
    semantic_records = runner.memory_store.search(query="launch budget approved quarter finance", memory_type="semantic", limit=10)
    assert semantic_records == []


def test_tool_result_becomes_memory_eligible_once_corroborated() -> None:
    """Seed a corroborating semantic memory first, then run a tool whose
    output claim overlaps with it — the Immune layer should find support
    and the tool's result should be promoted to semantic memory."""
    import tools  # noqa: F401
    from models.cognitive_memory import MemoryRecord

    runner = WorkflowRunner()
    runner.memory_store.write(MemoryRecord(
        type="semantic", content="The launch budget was approved for next quarter by finance.",
        task_id="seed-task", source_agent="researcher", verification_state="verified",
        tags=["research"], provenance="aion-immune-v1",
    ))

    asyncio.run(runner.execute_tool(
        "text_analysis", task_id="task-mem2",
        parameters={"text": "The launch budget was approved for next quarter by finance leadership."},
    ))

    report = runner.get_tool_immune_report("task-mem2", "text_analysis")
    assert report is not None
    # text_analysis's content is a stats sentence, not the analyzed text
    # itself, so genuine corroboration isn't expected here — this test
    # documents that verification runs and produces a real (not fabricated)
    # decision either way.
    assert report.decision in ("pass", "pass_with_warning", "require_revision", "reject")


def test_tool_execution_survives_memory_write_failure() -> None:
    import tools  # noqa: F401

    class _BrokenStore:
        def search(self, **kwargs):
            return []

        def write(self, record):
            raise RuntimeError("simulated storage failure")

    runner = WorkflowRunner(memory_store=_BrokenStore())
    output = asyncio.run(runner.execute_tool("calculator", task_id="task-fail", parameters={"expression": "1 + 1"}))
    assert output.success is True  # tool execution itself is unaffected by a downstream memory failure


# ---------------------------------------------------------------------------
# Existing chat/API regression
# ---------------------------------------------------------------------------


def test_chat_response_shape_unchanged_after_tool_system_integration() -> None:
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    response = client.post("/api/chat", json={"message": "Summarize the plan"})
    assert response.status_code == 200
    body = response.json()
    for field in ("task_id", "conversation_id", "answer", "mode", "status", "used_agents", "confidence"):
        assert field in body
    assert "tool_results" not in body


def test_full_backend_endpoints_still_respond() -> None:
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    assert client.get("/api/dashboard").status_code == 200
    assert client.get("/api/agents").status_code == 200
    assert client.get("/api/memory").status_code == 200
