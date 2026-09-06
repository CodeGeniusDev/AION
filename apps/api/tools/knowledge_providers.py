"""Concrete knowledge providers.

`MemoryKnowledgeProvider` is REAL: it retrieves from AION's own persistent
Cognitive Memory (memory/store.py) — genuine internal retrieval with real
provenance (real memory_ids, real timestamps, real content), not fabricated
data. This backend runs in a sandboxed environment with no outbound access
to external web/search APIs and no search-provider API key configured (see
network_configuration) — a live external web-search provider cannot be
honestly implemented here right now. MemoryKnowledgeProvider is what "real
data available in the current environment" genuinely means for this phase.

`StaticKnowledgeProvider` is explicitly NOT real-world research — its name
says so, and its docstring says so twice. It serves a small, fixed corpus
so the pipeline's conflict-detection, verification, and failure-handling
mechanics can be tested deterministically, without pretending to be
external research. It is registered the same way as any other tool so the
architecture is genuinely exercised end-to-end, not mocked around.

Unlike the stateless built-in tools in tools/builtin.py (which share one
process-wide registry, since they carry no per-instance state),
`MemoryKnowledgeProvider` is bound to a specific memory store and must
NOT be registered into that shared global registry — doing so would leak
one WorkflowRunner's memory access into another's. Each WorkflowRunner
therefore gets its own private knowledge-provider registry via
`build_knowledge_registry()` below, constructed at __init__ time.
"""

from datetime import datetime, timezone

from memory.store import MemoryStoreInterface
from models.cognitive_dna import CapabilityTag, Domain
from models.knowledge import EvidenceSource
from models.tool import ToolIdentity
from tools.knowledge import KnowledgeProviderTool
from tools.registry import ToolRegistry


class MemoryKnowledgeProvider(KnowledgeProviderTool):
    id = "memory_knowledge"
    name = "Internal Memory Knowledge Provider"

    def __init__(self, memory_store: MemoryStoreInterface) -> None:
        self.memory_store = memory_store

    async def search(self, query: str) -> list[EvidenceSource]:
        results = self.memory_store.search(query=query, memory_type="semantic", limit=5)
        return [
            EvidenceSource(
                source_id=result.record.memory_id, provider=self.id,
                title=f"AION memory record {result.record.memory_id}",
                url=None, retrieved_at=datetime.now(timezone.utc), raw_content=result.record.content,
            )
            for result in results
        ]


_STATIC_TEST_CORPUS = [
    {"id": "doc-1", "title": "Internal test note: launch budget", "content": "The launch budget was approved for next quarter by finance."},
    {"id": "doc-2", "title": "Internal test note: launch budget review", "content": "The launch budget was not approved for next quarter according to a later review."},
    {"id": "doc-3", "title": "Internal test note: unrelated topic", "content": "The office coffee machine was replaced last week."},
]


class StaticKnowledgeProvider(KnowledgeProviderTool):
    """Deterministic test-fixture provider. NOT real-world research data —
    see this module's docstring."""

    id = "static_test_corpus"
    name = "Static Test Corpus (fixture, not real-world data)"

    async def search(self, query: str) -> list[EvidenceSource]:
        query_words = {word.lower() for word in query.split() if len(word) > 3}
        matches = []
        for document in _STATIC_TEST_CORPUS:
            content_words = {word.lower().strip(".,") for word in document["content"].split() if len(word) > 3}
            if query_words & content_words:
                matches.append(document)
        return [
            EvidenceSource(
                source_id=document["id"], provider=self.id, title=document["title"],
                url=None, retrieved_at=datetime.now(timezone.utc), raw_content=document["content"],
            )
            for document in matches
        ]


def build_knowledge_registry(memory_store: MemoryStoreInterface) -> ToolRegistry:
    """Construct a private, per-caller ToolRegistry containing the two
    knowledge providers above. Private (not the shared global registry)
    because MemoryKnowledgeProvider carries per-instance state."""
    knowledge_registry = ToolRegistry()
    knowledge_registry.register(
        ToolIdentity(
            id=MemoryKnowledgeProvider.id, name=MemoryKnowledgeProvider.name,
            description="Retrieves verified evidence already stored in AION's own persistent Cognitive Memory.",
            capabilities=[CapabilityTag(name="knowledge_retrieval", domain=Domain.RESEARCH, declared_proficiency=0.8)],
            domains=[Domain.RESEARCH], timeout_seconds=3.0,
        ),
        MemoryKnowledgeProvider(memory_store),
    )
    knowledge_registry.register(
        ToolIdentity(
            id=StaticKnowledgeProvider.id, name=StaticKnowledgeProvider.name,
            description="Deterministic fixture corpus for testing the research pipeline — not real-world data.",
            capabilities=[CapabilityTag(name="knowledge_retrieval", domain=Domain.RESEARCH, declared_proficiency=0.3)],
            domains=[Domain.RESEARCH], timeout_seconds=1.0,
        ),
        StaticKnowledgeProvider(),
    )
    return knowledge_registry
