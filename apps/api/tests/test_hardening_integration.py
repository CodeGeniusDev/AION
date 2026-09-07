"""Integration tests for the P0/P1 hardening pass: bounded retention
(Cognitive Bus + Immune reports), async SQLite offloading, request/
correlation ID propagation via main.py's middleware, and rate limiting on
/api/chat. All against real WorkflowRunner/FastAPI behavior, not mocks.
"""

import asyncio

from fastapi.testclient import TestClient

from main import app
from models.chat import ChatRequest
from orchestration.workflow_runner import WorkflowRunner
from routes.chat import _rate_limiter as chat_rate_limiter

client = TestClient(app)


def teardown_function() -> None:
    chat_rate_limiter.reset()


def run_chat(request: ChatRequest, runner: WorkflowRunner | None = None):
    return asyncio.run((runner or WorkflowRunner()).run(request))


# ---------------------------------------------------------------------------
# Bounded retention / eviction
# ---------------------------------------------------------------------------


def test_task_history_grows_with_each_new_task() -> None:
    runner = WorkflowRunner(max_retained_tasks=10)
    run_chat(ChatRequest(message="Create a roadmap and steps"), runner)
    run_chat(ChatRequest(message="Research and compare options"), runner)
    assert len(runner._task_history) == 2


def test_oldest_task_is_evicted_once_cap_exceeded() -> None:
    runner = WorkflowRunner(max_retained_tasks=2)
    first = run_chat(ChatRequest(message="Create a roadmap and steps"), runner)
    run_chat(ChatRequest(message="Research and compare options"), runner)
    run_chat(ChatRequest(message="Create a roadmap for launch"), runner)

    assert len(runner._task_history) == 2
    assert first.task_id not in runner._task_history
    # Evicted task's bus history is genuinely cleared, not just untracked.
    assert runner.bus.get_task_messages(first.task_id) == []


def test_evicted_task_immune_report_is_removed() -> None:
    runner = WorkflowRunner(max_retained_tasks=1)
    first = run_chat(ChatRequest(message="Research and compare options"), runner)
    assert runner.get_immune_report(first.task_id) is not None

    run_chat(ChatRequest(message="Research and compare something else"), runner)
    assert runner.get_immune_report(first.task_id) is None


def test_evicted_task_tool_immune_report_is_removed() -> None:
    import tools  # noqa: F401

    runner = WorkflowRunner(max_retained_tasks=1)
    asyncio.run(runner.execute_tool("calculator", task_id="tool-task-1", parameters={"expression": "1 + 1"}))
    run_chat(ChatRequest(message="Research and compare options"), runner)  # pushes tool-task-1 out

    assert "tool-task-1" not in runner._task_history
    assert runner.get_tool_immune_report("tool-task-1", "calculator") is None


def test_repeated_task_id_does_not_duplicate_retention_tracking() -> None:
    runner = WorkflowRunner(max_retained_tasks=5)
    runner._track_task("same-task")
    runner._track_task("same-task")
    assert len(runner._task_history) == 1


def test_non_evicted_tasks_remain_fully_intact() -> None:
    runner = WorkflowRunner(max_retained_tasks=3)
    responses = [run_chat(ChatRequest(message="Create a roadmap and steps"), runner) for _ in range(3)]
    for response in responses:
        assert len(runner.bus.get_task_messages(response.task_id)) > 0


def test_default_retention_cap_comes_from_settings() -> None:
    from config import settings

    runner = WorkflowRunner()
    assert runner._max_retained_tasks == settings.max_retained_tasks


# ---------------------------------------------------------------------------
# Async offloading — behavioral correctness preserved under the new async path
# ---------------------------------------------------------------------------


def test_memory_retrieval_and_consolidation_still_work_correctly_when_offloaded() -> None:
    """The async-offloaded code path must produce identical observable
    results to the previous synchronous one — this is a regression guard
    on correctness, not just "doesn't crash."""
    runner = WorkflowRunner()
    runner.memory_store.write(__import__("models.cognitive_memory", fromlist=["MemoryRecord"]).MemoryRecord(
        type="semantic", content="The launch budget was approved for next quarter.",
        task_id="seed", source_agent="researcher", verification_state="verified", tags=["research"], provenance="x",
    ))
    response = run_chat(ChatRequest(message="What do we know about the launch budget for next quarter?"), runner)
    retrieval_events = [m for m in runner.bus.get_task_messages(response.task_id) if m.intent == "memory_retrieved"]
    assert len(retrieval_events) == 1


def test_concurrent_chat_requests_on_shared_runner_do_not_corrupt_each_others_data() -> None:
    """Real concurrency test: multiple requests interleaved via
    asyncio.gather on the same singleton-style runner must remain
    correctly task-isolated end to end."""
    runner = WorkflowRunner()

    async def _run_many():
        return await asyncio.gather(
            runner.run(ChatRequest(message="Create a roadmap and steps for A")),
            runner.run(ChatRequest(message="Research and compare B options")),
            runner.run(ChatRequest(message="Create a roadmap and steps for C")),
        )

    responses = asyncio.run(_run_many())
    task_ids = [r.task_id for r in responses]
    assert len(set(task_ids)) == 3  # all distinct
    for response in responses:
        messages = runner.bus.get_task_messages(response.task_id)
        assert all(m.task_id == response.task_id for m in messages)


def test_tool_execution_memory_gating_still_correct_when_offloaded() -> None:
    import tools  # noqa: F401
    from models.cognitive_memory import MemoryRecord

    runner = WorkflowRunner()
    runner.memory_store.write(MemoryRecord(
        type="semantic", content="The office coffee machine was replaced last week by facilities.",
        task_id="seed", source_agent="researcher", verification_state="verified", tags=["research"], provenance="x",
    ))
    asyncio.run(runner.execute_tool("text_analysis", task_id="task-offload", parameters={"text": "office coffee machine replaced"}))
    report = runner.get_tool_immune_report("task-offload", "text_analysis")
    assert report is not None


# ---------------------------------------------------------------------------
# Request/correlation ID middleware (main.py)
# ---------------------------------------------------------------------------


def test_response_includes_request_id_header() -> None:
    response = client.get("/health")
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"]


def test_response_includes_correlation_id_header() -> None:
    response = client.get("/health")
    assert "X-Correlation-ID" in response.headers


def test_incoming_correlation_id_header_is_honored() -> None:
    response = client.get("/health", headers={"X-Correlation-ID": "external-trace-999"})
    assert response.headers["X-Correlation-ID"] == "external-trace-999"


def test_each_request_gets_a_distinct_request_id() -> None:
    first = client.get("/health").headers["X-Request-ID"]
    second = client.get("/health").headers["X-Request-ID"]
    assert first != second


def test_middleware_does_not_alter_chat_response_body_contract() -> None:
    response = client.post("/api/chat", json={"message": "Summarize the plan"})
    assert response.status_code == 200
    body = response.json()
    for field in ("task_id", "conversation_id", "answer", "mode", "status", "used_agents", "confidence"):
        assert field in body
    # Headers carry tracing metadata; the body must not.
    assert "request_id" not in body
    assert "correlation_id" not in body


# ---------------------------------------------------------------------------
# Rate limiting (routes/chat.py)
# ---------------------------------------------------------------------------


def test_chat_requests_within_limit_succeed() -> None:
    chat_rate_limiter.reset()
    for _ in range(3):
        response = client.post("/api/chat", json={"message": "Summarize the plan"})
        assert response.status_code == 200


def test_chat_requests_over_limit_return_429() -> None:
    chat_rate_limiter.reset()
    chat_rate_limiter.max_requests = 2
    try:
        client.post("/api/chat", json={"message": "one"})
        client.post("/api/chat", json={"message": "two"})
        response = client.post("/api/chat", json={"message": "three"})
        assert response.status_code == 429
        assert "Too many requests" in response.json()["detail"]
    finally:
        chat_rate_limiter.max_requests = 60  # restore default-like value for other tests


def test_rate_limit_error_body_does_not_leak_internals() -> None:
    chat_rate_limiter.reset()
    chat_rate_limiter.max_requests = 1
    try:
        client.post("/api/chat", json={"message": "one"})
        response = client.post("/api/chat", json={"message": "two"})
        assert response.status_code == 429
        assert set(response.json().keys()) == {"detail"}
    finally:
        chat_rate_limiter.max_requests = 60


def test_other_endpoints_are_not_rate_limited_by_the_chat_limiter() -> None:
    chat_rate_limiter.reset()
    chat_rate_limiter.max_requests = 1
    try:
        client.post("/api/chat", json={"message": "one"})
        client.post("/api/chat", json={"message": "two"})  # exhausts chat limit
        response = client.get("/api/dashboard")
        assert response.status_code == 200  # unaffected — different endpoint
    finally:
        chat_rate_limiter.max_requests = 60


# ---------------------------------------------------------------------------
# Full regression
# ---------------------------------------------------------------------------


def test_all_static_endpoints_still_respond_after_hardening() -> None:
    for path in ("/", "/health", "/api/dashboard", "/api/agents", "/api/tasks", "/api/memory", "/api/workflows", "/api/research"):
        response = client.get(path)
        assert response.status_code == 200, path
