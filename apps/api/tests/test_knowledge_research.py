"""Tests for the Knowledge & Research Layer (models/knowledge.py,
tools/knowledge*.py, orchestration/research_pipeline.py).

Covers real provenance, provider discovery, conflict detection, Immune
verification of evidence, memory-write gating, timeout/failure/empty-result
handling, Cognitive Bus lifecycle events, and existing chat/API regression.
No fake success cases: every "verified" assertion below is produced by
actually running the pipeline against real (internal or fixture) data, not
asserted directly on a constructed object.
"""

import asyncio

from memory.store import SQLiteMemoryStore
from models.cognitive_memory import MemoryRecord
from orchestration.research_pipeline import ResearchPipeline
from orchestration.workflow_runner import WorkflowRunner
from tools.executor import ToolExecutor
from tools.knowledge_providers import MemoryKnowledgeProvider, StaticKnowledgeProvider, build_knowledge_registry


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_static_provider_returns_real_provenance_fields() -> None:
    provider = StaticKnowledgeProvider()
    sources = asyncio.run(provider.search("launch budget approved"))
    assert len(sources) >= 1
    for source in sources:
        assert source.provider == "static_test_corpus"
        assert source.title
        assert source.retrieved_at is not None
        assert source.raw_content


def test_memory_provider_returns_real_memory_ids_as_source_ids() -> None:
    store = SQLiteMemoryStore(":memory:")
    record = store.write(MemoryRecord(
        type="semantic", content="The launch budget was approved for next quarter.",
        task_id="t1", source_agent="researcher", verification_state="verified",
        tags=["research"], provenance="aion-immune-v1",
    ))
    provider = MemoryKnowledgeProvider(store)
    sources = asyncio.run(provider.search("launch budget approved quarter"))
    assert len(sources) == 1
    assert sources[0].source_id == record.memory_id
    assert sources[0].provider == "memory_knowledge"
    assert sources[0].url is None  # internal source genuinely has no URL


def test_static_provider_returns_empty_list_for_no_match_not_an_error() -> None:
    provider = StaticKnowledgeProvider()
    sources = asyncio.run(provider.search("completely unrelated zzz topic"))
    assert sources == []


# ---------------------------------------------------------------------------
# Knowledge provider tool wrapper (execute())
# ---------------------------------------------------------------------------


def test_knowledge_provider_execute_wraps_sources_in_tool_output() -> None:
    provider = StaticKnowledgeProvider()
    output = asyncio.run(provider.execute("t1", {"query": "launch budget approved"}))
    assert output.success is True
    assert len(output.data["sources"]) >= 1


def test_knowledge_provider_execute_requires_query_parameter() -> None:
    provider = StaticKnowledgeProvider()
    output = asyncio.run(provider.execute("t1", {}))
    assert output.success is False
    assert "query" in output.error


def test_knowledge_provider_execute_empty_results_is_still_success() -> None:
    provider = StaticKnowledgeProvider()
    output = asyncio.run(provider.execute("t1", {"query": "zzz nonmatching"}))
    assert output.success is True
    assert output.data["sources"] == []


# ---------------------------------------------------------------------------
# build_knowledge_registry: private per-instance registry, discoverable via
# Cognitive DNA capabilities
# ---------------------------------------------------------------------------


def test_knowledge_registry_providers_discoverable_by_domain() -> None:
    from models.cognitive_dna import Domain

    store = SQLiteMemoryStore(":memory:")
    registry = build_knowledge_registry(store)
    results = registry.find_by_capability(domain=Domain.RESEARCH, capability_name="knowledge_retrieval")
    ids = {identity.id for identity in results}
    assert ids == {"memory_knowledge", "static_test_corpus"}


def test_two_knowledge_registries_are_isolated_per_memory_store() -> None:
    """Confirms the private-registry-per-instance design actually isolates
    memory access — this is the whole reason it isn't a shared singleton."""
    store_a = SQLiteMemoryStore(":memory:")
    store_a.write(MemoryRecord(
        type="semantic", content="Store A has a unique budget fact here.",
        task_id="t", source_agent="x", verification_state="verified", tags=[], provenance="x",
    ))
    store_b = SQLiteMemoryStore(":memory:")

    registry_a = build_knowledge_registry(store_a)
    registry_b = build_knowledge_registry(store_b)

    provider_a = registry_a.get_tool("memory_knowledge")
    provider_b = registry_b.get_tool("memory_knowledge")

    results_a = asyncio.run(provider_a.search("unique budget fact"))
    results_b = asyncio.run(provider_b.search("unique budget fact"))

    assert len(results_a) == 1
    assert results_b == []


# ---------------------------------------------------------------------------
# ResearchPipeline: discovery, retrieval, normalization
# ---------------------------------------------------------------------------


def test_research_finds_sources_from_static_provider() -> None:
    runner = WorkflowRunner()
    result = asyncio.run(runner.research("launch budget approved quarter", task_id="t1", provider_ids=["static_test_corpus"]))
    assert len(result.all_sources) >= 1
    assert result.query == "launch budget approved quarter"
    assert result.task_id == "t1"


def test_research_with_no_provider_ids_uses_domain_discovery() -> None:
    runner = WorkflowRunner()
    result = asyncio.run(runner.research("launch budget approved quarter", task_id="t2"))
    assert len(result.all_sources) >= 1


def test_research_empty_query_result_returns_no_sources_no_error() -> None:
    runner = WorkflowRunner()
    result = asyncio.run(runner.research("zzz nonmatching query xyz", task_id="t3", provider_ids=["static_test_corpus"]))
    assert result.all_sources == []
    assert result.evidence == []
    assert result.provider_errors == []


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def test_research_detects_conflicting_sources() -> None:
    """The static corpus intentionally contains two overlapping,
    negation-mismatched documents about the launch budget."""
    runner = WorkflowRunner()
    result = asyncio.run(runner.research("launch budget approved quarter", task_id="t4", provider_ids=["static_test_corpus"]))
    assert len(result.conflicts) >= 1
    conflict = result.conflicts[0]
    assert conflict.evidence_a_id != conflict.evidence_b_id


def test_conflicting_sources_are_not_both_marked_verified() -> None:
    runner = WorkflowRunner()
    result = asyncio.run(runner.research("launch budget approved quarter", task_id="t5", provider_ids=["static_test_corpus"]))
    assert result.evidence == []


def test_unrelated_sources_produce_no_conflict() -> None:
    runner = WorkflowRunner()
    result = asyncio.run(runner.research("office coffee machine replaced", task_id="t6", provider_ids=["static_test_corpus"]))
    assert result.conflicts == []


# ---------------------------------------------------------------------------
# Verification / memory eligibility
# ---------------------------------------------------------------------------


def test_uncorroborated_single_source_is_not_verified() -> None:
    runner = WorkflowRunner()
    result = asyncio.run(runner.research("office coffee machine replaced", task_id="t7", provider_ids=["static_test_corpus"]))
    assert len(result.all_sources) == 1
    assert result.evidence == []


def test_corroborated_evidence_across_providers_becomes_verified() -> None:
    runner = WorkflowRunner()
    runner.memory_store.write(MemoryRecord(
        type="semantic", content="The office coffee machine was replaced last week by facilities.",
        task_id="seed", source_agent="researcher", verification_state="verified", tags=["research"], provenance="aion-immune-v1",
    ))
    result = asyncio.run(runner.research(
        "office coffee machine replaced", task_id="t8", provider_ids=["static_test_corpus", "memory_knowledge"],
    ))
    assert len(result.evidence) == 2
    assert all(e.verification_state == "verified" for e in result.evidence)


def test_verified_evidence_is_written_to_semantic_memory() -> None:
    runner = WorkflowRunner()
    runner.memory_store.write(MemoryRecord(
        type="semantic", content="The office coffee machine was replaced last week by facilities.",
        task_id="seed", source_agent="researcher", verification_state="verified", tags=["research"], provenance="aion-immune-v1",
    ))
    count_before = runner.memory_store.count()
    asyncio.run(runner.research("office coffee machine replaced", task_id="t9", provider_ids=["static_test_corpus", "memory_knowledge"]))
    assert runner.memory_store.count() > count_before


def test_research_with_memory_disabled_never_writes_or_reads_memory() -> None:
    runner = WorkflowRunner(enable_memory_persistence=False)
    result = asyncio.run(runner.research("launch budget approved quarter", task_id="t10", provider_ids=["static_test_corpus"]))
    assert runner.memory_store.count() == 0
    assert result is not None


# ---------------------------------------------------------------------------
# Failure / timeout / unknown-provider handling
# ---------------------------------------------------------------------------


def test_research_handles_unknown_provider_gracefully() -> None:
    runner = WorkflowRunner()
    result = asyncio.run(runner.research("anything", task_id="t11", provider_ids=["does-not-exist"]))
    assert result.all_sources == []
    assert len(result.provider_errors) == 1
    assert "does-not-exist" in result.provider_errors[0]


def test_research_continues_when_one_provider_fails_and_another_succeeds() -> None:
    runner = WorkflowRunner()
    result = asyncio.run(runner.research(
        "launch budget approved quarter", task_id="t12", provider_ids=["does-not-exist", "static_test_corpus"],
    ))
    assert len(result.provider_errors) == 1
    assert len(result.all_sources) >= 1


def test_research_provider_timeout_is_isolated() -> None:
    from cognitive_bus import CognitiveBus
    from immune.system import ImmuneSystem
    from models.cognitive_dna import CapabilityTag, Domain
    from models.tool import ToolIdentity
    from tools.base import BaseTool
    from tools.registry import ToolRegistry

    class _SlowProvider(BaseTool):
        id = "slow_knowledge"
        name = "Slow"

        async def execute(self, task_id, parameters):
            await asyncio.sleep(10)

    registry = ToolRegistry()
    registry.register(
        ToolIdentity(
            id="slow_knowledge", name="Slow", description="d",
            capabilities=[CapabilityTag(name="knowledge_retrieval", domain=Domain.RESEARCH)],
            domains=[Domain.RESEARCH], timeout_seconds=0.05,
        ),
        _SlowProvider(),
    )
    executor = ToolExecutor(registry)
    pipeline = ResearchPipeline(tool_registry=registry, tool_executor=executor, immune_system=ImmuneSystem(), memory_store=None, bus=CognitiveBus())
    result = asyncio.run(pipeline.research("anything", task_id="t13", provider_ids=["slow_knowledge"]))
    assert result.all_sources == []
    assert len(result.provider_errors) == 1
    assert "timed out" in result.provider_errors[0]


# ---------------------------------------------------------------------------
# Cognitive Bus lifecycle events
# ---------------------------------------------------------------------------


def test_research_publishes_full_lifecycle_events() -> None:
    runner = WorkflowRunner()
    asyncio.run(runner.research("launch budget approved quarter", task_id="t14", provider_ids=["static_test_corpus"]))
    intents = [m.intent for m in runner.bus.get_task_messages("t14")]
    assert intents[0] == "research_requested"
    assert intents[-1] == "research_completed"
    assert "research_provider_started" in intents
    assert "research_source_retrieved" in intents
    assert "research_conflict_detected" in intents


def test_research_publishes_provider_failed_event() -> None:
    runner = WorkflowRunner()
    asyncio.run(runner.research("anything", task_id="t15", provider_ids=["does-not-exist"]))
    intents = [m.intent for m in runner.bus.get_task_messages("t15")]
    assert "research_provider_failed" in intents


def test_research_tasks_remain_isolated_on_the_bus() -> None:
    runner = WorkflowRunner()
    asyncio.run(runner.research("launch budget approved quarter", task_id="task-alpha", provider_ids=["static_test_corpus"]))
    asyncio.run(runner.research("office coffee machine replaced", task_id="task-beta", provider_ids=["static_test_corpus"]))
    alpha_messages = runner.bus.get_task_messages("task-alpha")
    beta_messages = runner.bus.get_task_messages("task-beta")
    assert all(m.task_id == "task-alpha" for m in alpha_messages)
    assert all(m.task_id == "task-beta" for m in beta_messages)


# ---------------------------------------------------------------------------
# Existing chat/API regression
# ---------------------------------------------------------------------------


def test_chat_response_shape_unchanged_after_research_layer_integration() -> None:
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    response = client.post("/api/chat", json={"message": "Summarize the plan"})
    assert response.status_code == 200
    body = response.json()
    for field in ("task_id", "conversation_id", "answer", "mode", "status", "used_agents", "confidence"):
        assert field in body
    assert "research" not in body
    assert "evidence" not in body


def test_existing_static_research_dashboard_endpoint_is_unaffected() -> None:
    """/api/research is a pre-existing, unrelated frontend demo endpoint
    (static research notes) — confirm the naming-collision fix left it
    fully intact."""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    response = client.get("/api/research")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body


def test_full_backend_endpoints_still_respond() -> None:
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    assert client.get("/api/dashboard").status_code == 200
    assert client.get("/api/agents").status_code == 200
    assert client.get("/api/memory").status_code == 200
    assert client.get("/api/workflows").status_code == 200
    assert client.get("/api/tasks").status_code == 200
