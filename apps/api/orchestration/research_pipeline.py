"""Research workflow: discover -> retrieve -> normalize -> verify -> evidence.

Reuses immune/evidence.py's lexical heuristics directly for conflict
detection (imported, not reimplemented) and immune/system.py's
ImmuneSystem for verification — knowledge evidence is treated exactly like
an agent claim, because the Immune System doesn't (and shouldn't) care
about source type, only about corroboration. This is the "build on the
existing Tool/Immune architecture, don't create a parallel one" requirement
made concrete.
"""

import asyncio

from cognitive_bus import CognitiveBus, CognitiveMessage
from immune.evidence import has_negation, keywords, overlap_ratio
from immune.system import ImmuneSystem
from memory.store import MemoryStoreInterface
from models.cognitive_dna import Domain
from models.cognitive_memory import MemoryRecord
from models.knowledge import Evidence, EvidenceSource, ResearchConflict, ResearchResult
from models.verification import ClaimRecord
from tools.executor import ToolExecutor
from tools.registry import ToolRegistryInterface

_STATUS_TO_VERIFICATION_STATE = {
    "verified": "verified",
    "partially_verified": "uncertain",
    "insufficient_evidence": "uncertain",
    "contradicted": "contradicted",
}
_CONFLICT_OVERLAP_THRESHOLD = 0.3


class ResearchPipeline:
    def __init__(
        self, *, tool_registry: ToolRegistryInterface, tool_executor: ToolExecutor,
        immune_system: ImmuneSystem, memory_store: MemoryStoreInterface | None, bus: CognitiveBus,
    ) -> None:
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.immune_system = immune_system
        self.memory_store = memory_store
        self.bus = bus

    async def research(self, query: str, *, task_id: str, provider_ids: list[str] | None = None) -> ResearchResult:
        bus = self.bus
        bus.publish(CognitiveMessage(
            task_id=task_id, source_agent="aion", target_agent=None, intent="research_requested",
            content=f"Research requested: {query}", status="pending",
        ))

        providers = provider_ids or [
            identity.id for identity in self.tool_registry.find_by_capability(
                domain=Domain.RESEARCH, capability_name="knowledge_retrieval", available_only=True,
            )
        ]

        all_sources: list[EvidenceSource] = []
        provider_errors: list[str] = []
        for provider_id in providers:
            bus.publish(CognitiveMessage(
                task_id=task_id, source_agent="aion", target_agent=None, intent="research_provider_started",
                content=f"Querying provider '{provider_id}'", status="processing",
            ))
            output = await self.tool_executor.execute(provider_id, task_id=task_id, parameters={"query": query})
            if not output.success:
                provider_errors.append(f"{provider_id}: {output.error}")
                bus.publish(CognitiveMessage(
                    task_id=task_id, source_agent=f"knowledge:{provider_id}", target_agent=None,
                    intent="research_provider_failed", content=output.error or "unknown error", status="failed",
                ))
                continue
            raw_sources = output.data.get("sources", [])
            sources = [EvidenceSource.model_validate(item) for item in raw_sources]
            all_sources.extend(sources)
            bus.publish(CognitiveMessage(
                task_id=task_id, source_agent=f"knowledge:{provider_id}", target_agent=None,
                intent="research_source_retrieved", content=f"{len(sources)} source(s) retrieved",
                context={"provider": provider_id, "count": len(sources)}, status="completed",
            ))

        if not all_sources:
            bus.publish(CognitiveMessage(
                task_id=task_id, source_agent="aion", target_agent=None, intent="research_completed",
                content="No sources found.", context={"evidence_count": 0, "conflicts": 0}, status="completed",
            ))
            return ResearchResult(query=query, task_id=task_id, provider_errors=provider_errors)

        candidates = [
            Evidence(task_id=task_id, provider_id=source.provider, source=source, content=source.raw_content.strip())
            for source in all_sources
        ]

        conflicts: list[ResearchConflict] = []
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                a, b = candidates[i], candidates[j]
                if (
                    overlap_ratio(keywords(a.content), keywords(b.content)) >= _CONFLICT_OVERLAP_THRESHOLD
                    and has_negation(a.content) != has_negation(b.content)
                ):
                    conflicts.append(ResearchConflict(
                        evidence_a_id=a.evidence_id, evidence_b_id=b.evidence_id,
                        description="Overlapping evidence with a negation mismatch — possible contradiction.",
                    ))
        for conflict in conflicts:
            bus.publish(CognitiveMessage(
                task_id=task_id, source_agent="aion", target_agent=None, intent="research_conflict_detected",
                content=conflict.description,
                context={"evidence_a": conflict.evidence_a_id, "evidence_b": conflict.evidence_b_id}, status="completed",
            ))

        verified_evidence: list[Evidence] = []
        for index, candidate in enumerate(candidates):
            peer_statements = [(c.provider_id, c.content) for other_index, c in enumerate(candidates) if other_index != index]
            memory_context = (
                [
                    result.record.content
                    for result in await asyncio.to_thread(self.memory_store.search, query=candidate.content, memory_type="semantic", limit=5)
                ]
                if self.memory_store is not None else []
            )
            claim = ClaimRecord(text=candidate.content[:500], source_agent=f"knowledge:{candidate.provider_id}", task_id=task_id)
            result = self.immune_system.verify_claim(claim, memory=memory_context, peer_statements=peer_statements)
            candidate.verification_state = _STATUS_TO_VERIFICATION_STATE[result.status]

            if result.status == "verified":
                verified_evidence.append(candidate)
                if self.memory_store is not None:
                    try:
                        await asyncio.to_thread(self.memory_store.write, MemoryRecord(
                            type="semantic", content=candidate.content, task_id=task_id,
                            source_agent=f"knowledge:{candidate.provider_id}", verification_state="verified",
                            tags=["research"], provenance=f"knowledge:{candidate.provider_id}",
                        ))
                    except Exception:
                        pass  # a memory write failure must never break the research pipeline

        bus.publish(CognitiveMessage(
            task_id=task_id, source_agent="aion", target_agent=None, intent="research_completed",
            content=f"Research complete: {len(verified_evidence)} verified evidence item(s) from {len(all_sources)} source(s).",
            context={"evidence_count": len(verified_evidence), "conflicts": len(conflicts), "sources_considered": len(all_sources)},
            status="completed",
        ))
        return ResearchResult(
            query=query, task_id=task_id, evidence=verified_evidence,
            all_sources=all_sources, conflicts=conflicts, provider_errors=provider_errors,
        )
