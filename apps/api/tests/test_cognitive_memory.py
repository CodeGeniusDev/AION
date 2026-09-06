"""Tests for the Cognitive Memory layer (memory/*.py, models/cognitive_memory.py).

Covers persistence, retrieval relevance, task isolation, the verified-only
write policy for semantic memory (contradiction protection), failure
safety, and WorkflowRunner integration / chat regression.
"""

import asyncio

import pytest

from immune.system import ImmuneSystem
from memory.consolidation import consolidate_task_memory
from memory.embeddings import EmbeddingProvider, NullEmbeddingProvider
from memory.store import SQLiteMemoryStore
from models.chat import ChatRequest
from models.cognitive_memory import MemoryRecord
from models.verification import ClaimRecord, ImmuneReport, VerificationResult
from orchestration.workflow_runner import WorkflowRunner


def _record(**overrides) -> MemoryRecord:
    defaults = dict(
        type="semantic", content="The launch budget was approved for next quarter.",
        task_id="task-A", source_agent="aion", verification_state="verified",
        tags=["research"], provenance="aion-immune-v1",
    )
    defaults.update(overrides)
    return MemoryRecord(**defaults)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_write_then_get_round_trip() -> None:
    store = SQLiteMemoryStore(":memory:")
    record = store.write(_record())
    fetched = store.get(record.memory_id)
    assert fetched is not None
    assert fetched.content == record.content
    assert fetched.verification_state == "verified"


def test_get_unknown_memory_id_returns_none() -> None:
    store = SQLiteMemoryStore(":memory:")
    assert store.get("does-not-exist") is None


def test_count_reflects_writes() -> None:
    store = SQLiteMemoryStore(":memory:")
    assert store.count() == 0
    store.write(_record())
    store.write(_record(content="A second, different memory record here."))
    assert store.count() == 2


def test_clear_removes_all_records() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(_record())
    store.clear()
    assert store.count() == 0


def test_metadata_fields_are_persisted_correctly() -> None:
    store = SQLiteMemoryStore(":memory:")
    record = store.write(_record(source_agent="researcher", tags=["research", "budget"], provenance="aion-immune-v1"))
    fetched = store.get(record.memory_id)
    assert fetched.source_agent == "researcher"
    assert fetched.tags == ["research", "budget"]
    assert fetched.provenance == "aion-immune-v1"
    assert fetched.created_at is not None


# ---------------------------------------------------------------------------
# Retrieval relevance
# ---------------------------------------------------------------------------


def test_search_finds_lexically_relevant_record() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(_record(content="The launch budget was approved for next quarter."))
    results = store.search(query="What happened with the launch budget?", limit=5)
    assert len(results) == 1
    assert results[0].relevance_score > 0.0


def test_search_excludes_unrelated_record() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(_record(content="The weather today is sunny and warm outside."))
    results = store.search(query="What happened with the launch budget?", limit=5)
    assert results == []


def test_search_ranks_more_relevant_record_higher() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(_record(content="The launch budget was approved for next quarter by finance."))
    store.write(_record(content="The launch budget quarter finance approval decision was recorded."))
    results = store.search(query="launch budget approved quarter finance", limit=5)
    assert len(results) == 2
    assert results[0].relevance_score >= results[1].relevance_score


def test_search_respects_limit() -> None:
    store = SQLiteMemoryStore(":memory:")
    for i in range(10):
        store.write(_record(content=f"The launch budget item number {i} was approved for next quarter."))
    results = store.search(query="launch budget approved quarter", limit=3)
    assert len(results) == 3


def test_search_filters_by_memory_type() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(_record(type="semantic", content="The launch budget was approved for next quarter."))
    store.write(_record(type="episodic", content="Task ran and discussed the launch budget for next quarter."))
    results = store.search(query="launch budget quarter", memory_type="semantic", limit=5)
    assert all(result.record.type == "semantic" for result in results)


def test_search_filters_by_tags() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(_record(content="The launch budget was approved for next quarter.", tags=["finance"]))
    store.write(_record(content="The launch budget review needs a decision for next quarter.", tags=["planning"]))
    results = store.search(query="launch budget quarter", tags=["finance"], limit=5)
    assert len(results) == 1
    assert results[0].record.tags == ["finance"]


class _FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic fake used only to test the embedding code path exists
    and is genuinely used when available — not a claim about real semantics."""

    def embed(self, text: str) -> list[float] | None:
        return [float(len(text) % 7), float(text.count("a"))]


def test_search_uses_embeddings_when_a_provider_is_configured() -> None:
    store = SQLiteMemoryStore(":memory:", embedding_provider=_FakeEmbeddingProvider())
    store.write(_record(content="alpha alpha alpha alpha"))
    results = store.search(query="alpha alpha alpha alpha", limit=5)
    assert len(results) == 1
    assert results[0].relevance_score == 1.0  # identical fake vectors -> cosine similarity 1.0


def test_null_embedding_provider_always_returns_none() -> None:
    assert NullEmbeddingProvider().embed("anything") is None


# ---------------------------------------------------------------------------
# Task isolation
# ---------------------------------------------------------------------------


def test_list_for_task_returns_only_that_tasks_records() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(_record(task_id="task-A", content="Task A specific content about the budget."))
    store.write(_record(task_id="task-B", content="Task B specific content about the schedule."))
    task_a_records = store.list_for_task("task-A")
    assert len(task_a_records) == 1
    assert task_a_records[0].task_id == "task-A"


def test_list_for_task_on_unknown_task_returns_empty_list() -> None:
    store = SQLiteMemoryStore(":memory:")
    assert store.list_for_task("never-existed") == []


def test_records_from_different_tasks_never_mix_provenance() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(_record(task_id="task-A", source_agent="planner", content="Task A budget decision made today."))
    store.write(_record(task_id="task-B", source_agent="researcher", content="Task B schedule decision made today."))
    for record in store.list_for_task("task-A"):
        assert record.task_id == "task-A"
        assert record.source_agent == "planner"


# ---------------------------------------------------------------------------
# Verified-only write policy / contradiction protection
# ---------------------------------------------------------------------------


def test_consolidation_never_writes_contradicted_claims() -> None:
    store = SQLiteMemoryStore(":memory:")
    contradicted = VerificationResult(
        claim=ClaimRecord(text="The budget was definitely approved.", source_agent="aion", task_id="t1"),
        status="contradicted", risk="high", reasoning_summary="conflict found",
    )
    report = ImmuneReport(task_id="t1", claims_checked=1, verification_results=[contradicted], decision="require_revision", decision_reason="x")

    written = consolidate_task_memory(
        task_id="t1", mode="auto", execution_order=["researcher"], decision_reason="test",
        status="completed", required_domains=["research"], immune_report=report, store=store,
    )

    semantic_records = [r for r in written if r.type == "semantic"]
    assert semantic_records == []
    assert all(record.verification_state != "contradicted" for record in store.list_for_task("t1"))


def test_consolidation_never_writes_insufficient_evidence_claims() -> None:
    store = SQLiteMemoryStore(":memory:")
    insufficient = VerificationResult(
        claim=ClaimRecord(text="The roadmap includes three milestones.", source_agent="aion", task_id="t2"),
        status="insufficient_evidence", risk="medium", reasoning_summary="no evidence",
    )
    report = ImmuneReport(task_id="t2", claims_checked=1, verification_results=[insufficient], decision="pass_with_warning", decision_reason="x")

    written = consolidate_task_memory(
        task_id="t2", mode="auto", execution_order=["researcher"], decision_reason="test",
        status="completed", required_domains=[], immune_report=report, store=store,
    )
    assert [r for r in written if r.type == "semantic"] == []


def test_consolidation_writes_only_verified_claims_as_semantic_memory() -> None:
    store = SQLiteMemoryStore(":memory:")
    verified = VerificationResult(
        claim=ClaimRecord(text="The budget was approved for next quarter.", source_agent="researcher", task_id="t3"),
        status="verified", risk="low", reasoning_summary="supported",
    )
    contradicted = VerificationResult(
        claim=ClaimRecord(text="The schedule was finalized yesterday.", source_agent="researcher", task_id="t3"),
        status="contradicted", risk="high", reasoning_summary="conflict",
    )
    report = ImmuneReport(task_id="t3", claims_checked=2, verification_results=[verified, contradicted], decision="require_revision", decision_reason="x")

    written = consolidate_task_memory(
        task_id="t3", mode="auto", execution_order=["researcher"], decision_reason="test",
        status="completed", required_domains=["research"], immune_report=report, store=store,
    )

    semantic_records = [r for r in written if r.type == "semantic"]
    assert len(semantic_records) == 1
    assert semantic_records[0].content == "The budget was approved for next quarter."
    assert semantic_records[0].verification_state == "verified"


def test_consolidation_always_writes_exactly_one_episodic_record() -> None:
    store = SQLiteMemoryStore(":memory:")
    written = consolidate_task_memory(
        task_id="t4", mode="auto", execution_order=["planner"], decision_reason="test",
        status="completed", required_domains=["planning"], immune_report=None, store=store,
    )
    episodic_records = [r for r in written if r.type == "episodic"]
    assert len(episodic_records) == 1
    assert episodic_records[0].verification_state == "unverified"


def test_consolidation_with_no_immune_report_writes_only_episodic() -> None:
    store = SQLiteMemoryStore(":memory:")
    written = consolidate_task_memory(
        task_id="t5", mode="auto", execution_order=[], decision_reason="test",
        status="completed", required_domains=[], immune_report=None, store=store,
    )
    assert len(written) == 1
    assert written[0].type == "episodic"


def test_consolidation_does_not_store_every_claim_blindly() -> None:
    """A draft with many extractable claims, none verified, must still
    produce at most the one episodic record — no semantic pollution."""
    store = SQLiteMemoryStore(":memory:")
    immune = ImmuneSystem()
    report = immune.evaluate(
        task_id="t6",
        draft="The first claim here is unverified. The second claim here is also unverified. A third one too.",
        used_agent_outputs={}, memory=[],
    )
    written = consolidate_task_memory(
        task_id="t6", mode="auto", execution_order=["researcher"], decision_reason="test",
        status="completed", required_domains=[], immune_report=report, store=store,
    )
    assert len(written) == 1  # episodic only; nothing was verified


# ---------------------------------------------------------------------------
# Failure safety
# ---------------------------------------------------------------------------


class _BrokenStore(SQLiteMemoryStore):
    def write(self, record):  # noqa: ANN001
        raise RuntimeError("simulated storage failure")


def test_consolidation_failure_propagates_to_caller_not_silently_swallowed() -> None:
    """consolidate_task_memory itself does not catch errors — the fail-safe
    boundary is WorkflowRunner._consolidate_memory (tested below), keeping
    the pure function honest about failures rather than hiding them."""
    store = _BrokenStore(":memory:")
    with pytest.raises(RuntimeError):
        consolidate_task_memory(
            task_id="t7", mode="auto", execution_order=[], decision_reason="test",
            status="completed", required_domains=[], immune_report=None, store=store,
        )


def test_workflow_runner_survives_memory_storage_failure() -> None:
    runner = WorkflowRunner(memory_store=_BrokenStore(":memory:"))
    response = asyncio.run(runner.run(ChatRequest(message="Create a roadmap and steps for launch")))
    assert response.status == "completed"  # chat still succeeds despite storage failure

    failure_events = [
        m for m in runner.bus.get_task_messages(response.task_id) if m.intent == "memory_write_failed"
    ]
    assert len(failure_events) == 1


# ---------------------------------------------------------------------------
# WorkflowRunner integration
# ---------------------------------------------------------------------------


def run_chat(request: ChatRequest, runner: WorkflowRunner | None = None):
    return asyncio.run((runner or WorkflowRunner()).run(request))


def test_workflow_runner_writes_episodic_memory_after_task() -> None:
    runner = WorkflowRunner()
    response = run_chat(ChatRequest(message="Create a roadmap and steps for launch"), runner)
    task_records = runner.memory_store.list_for_task(response.task_id)
    assert any(record.type == "episodic" for record in task_records)


def test_workflow_runner_publishes_memory_write_bus_event() -> None:
    runner = WorkflowRunner()
    response = run_chat(ChatRequest(message="Create a roadmap and steps for launch"), runner)
    intents = [m.intent for m in runner.bus.get_task_messages(response.task_id)]
    assert "memory_write" in intents


def test_workflow_runner_retrieves_relevant_memory_for_a_later_task() -> None:
    runner = WorkflowRunner()
    # Seed a semantic memory directly (bypassing the need for a live model
    # to produce a genuinely agreeing claim in dev mode — see Phase F's
    # documented limitation about dev-mode fallback text being generic).
    runner.memory_store.write(_record(
        content="The launch budget was approved for next quarter.",
        task_id="seed-task", source_agent="researcher", tags=["research"],
    ))

    response = run_chat(ChatRequest(message="What do we know about the launch budget for next quarter?"), runner)

    retrieval_events = [m for m in runner.bus.get_task_messages(response.task_id) if m.intent == "memory_retrieved"]
    assert len(retrieval_events) == 1
    assert retrieval_events[0].context["count"] == 1


def test_memory_disabled_flag_skips_persistence_entirely() -> None:
    runner = WorkflowRunner(enable_memory_persistence=False)
    response = run_chat(ChatRequest(message="Create a roadmap and steps for launch"), runner)
    assert runner.memory_store.count() == 0
    intents = [m.intent for m in runner.bus.get_task_messages(response.task_id)]
    assert "memory_write" not in intents
    assert "memory_retrieved" not in intents


def test_memory_persists_across_multiple_requests_on_same_runner() -> None:
    runner = WorkflowRunner()
    run_chat(ChatRequest(message="Create a roadmap and steps for launch"), runner)
    run_chat(ChatRequest(message="Research and compare solar options"), runner)
    assert runner.memory_store.count() >= 2  # at least one episodic record per task


# ---------------------------------------------------------------------------
# Existing chat/API regression
# ---------------------------------------------------------------------------


def test_chat_response_shape_unchanged_after_memory_integration() -> None:
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    response = client.post("/api/chat", json={"message": "Summarize the plan"})
    assert response.status_code == 200
    body = response.json()
    for field in ("task_id", "conversation_id", "answer", "mode", "status", "used_agents", "confidence"):
        assert field in body
    assert "memory_records" not in body


def test_memory_dashboard_endpoint_unchanged() -> None:
    """The frontend's /api/memory demo endpoint is a separate concern from
    Cognitive Memory (it displays static category cards, not real
    records) — confirm it is genuinely untouched."""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    response = client.get("/api/memory")
    assert response.status_code == 200
    body = response.json()
    assert "categories" in body
    assert "policies" in body
