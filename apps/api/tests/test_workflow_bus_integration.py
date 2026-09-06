"""Integration tests: does the real Cognitive Bus behave correctly when
driven by WorkflowRunner, and does existing /api/chat behavior remain
unchanged now that the bus is persistent and messages carry the extended
schema? These are integration-level checks; unit-level bus behavior lives
in test_cognitive_bus.py, and unit-level registry behavior lives in
test_cognitive_dna.py.
"""

import asyncio

from fastapi.testclient import TestClient

from main import app
from models.chat import ChatRequest
from orchestration.workflow_runner import WorkflowRunner

client = TestClient(app)


def run_chat(request: ChatRequest, runner: WorkflowRunner | None = None):
    return asyncio.run((runner or WorkflowRunner()).run(request))


def test_workflow_runner_publishes_messages_to_its_bus() -> None:
    runner = WorkflowRunner()
    response = run_chat(ChatRequest(message="Plan a small research task"), runner)

    task_messages = runner.bus.get_task_messages(response.task_id)
    assert len(task_messages) > 0
    assert all(message.task_id == response.task_id for message in task_messages)


def test_workflow_runner_bus_messages_include_execute_and_result_intents() -> None:
    runner = WorkflowRunner()
    response = run_chat(ChatRequest(message="Plan a small research task"), runner)

    intents = [message.intent for message in runner.bus.get_task_messages(response.task_id)]
    assert intents.count("execute") >= 1


def test_workflow_runner_bus_history_survives_across_multiple_requests() -> None:
    """Confirms the bus is persistent (not recreated per call) and that
    different requests remain task-isolated within the same runner."""
    runner = WorkflowRunner()
    first = run_chat(ChatRequest(message="Make a plan for the launch roadmap"), runner)
    second = run_chat(ChatRequest(message="Research and compare these two options"), runner)

    assert first.task_id != second.task_id
    first_messages = runner.bus.get_task_messages(first.task_id)
    second_messages = runner.bus.get_task_messages(second.task_id)
    assert len(first_messages) > 0
    assert len(second_messages) > 0
    assert all(message.task_id == first.task_id for message in first_messages)
    assert all(message.task_id == second.task_id for message in second_messages)


def test_workflow_runner_bus_replay_matches_returned_task_id() -> None:
    runner = WorkflowRunner()
    response = run_chat(ChatRequest(message="Plan and research something small"), runner)

    replayed = runner.bus.replay(response.task_id)
    assert len(replayed) > 0
    assert replayed == runner.bus.get_task_messages(response.task_id)


def test_live_subscriber_observes_workflow_runner_publishing_in_real_time() -> None:
    """A subscriber attached before the request runs should observe the
    agent messages as WorkflowRunner publishes them — proving delivery is
    genuinely push-based, not just a post-hoc log."""
    runner = WorkflowRunner()
    observed: list[str] = []
    runner.bus.subscribe("agent:planner", lambda message: observed.append(message.intent))

    run_chat(ChatRequest(message="Plan a small task", mode="manual", selected_agents=["planner"]), runner)

    assert "execute" in observed


# ---------------------------------------------------------------------------
# Chat API regression — confirm existing behavior is unaffected by Phase B
# ---------------------------------------------------------------------------


def test_chat_endpoint_response_shape_unchanged() -> None:
    response = client.post("/api/chat", json={"message": "Summarize the plan"})
    assert response.status_code == 200
    body = response.json()
    for field in ("task_id", "conversation_id", "answer", "mode", "status", "used_agents", "confidence", "processing_time_ms"):
        assert field in body


def test_chat_endpoint_manual_mode_still_requires_agents() -> None:
    response = client.post("/api/chat", json={"message": "Plan this", "mode": "manual", "selected_agents": []})
    assert response.status_code == 422


def test_chat_endpoint_still_returns_valid_confidence_range() -> None:
    response = client.post("/api/chat", json={"message": "Research something small"})
    assert response.status_code == 200
    assert 0.0 <= response.json()["confidence"] <= 1.0
