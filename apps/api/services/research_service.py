"""Research API service.

Sources real data from Immune-verified semantic memory records tagged
"research" — either written by the real ResearchPipeline
(orchestration/research_pipeline.py, provenance="knowledge:<provider>") or
by chat consolidation when a research-domain task produced a verified claim
(memory/consolidation.py, tags include "research"). These are genuine
findings AION actually verified and stored, not fabricated research.

`type` is presentational categorization only — semantic memory records
have no native equivalent to the frontend's three-way
Architecture-note/Experiment/Working-draft split, so every real research
record is labeled "Experiment" (the closest fit: a verified finding from
actual system operation). This is documented here rather than silently
invented as a meaningful distinction.
"""

from memory.store import MemoryStoreInterface
from models.research import ResearchNote, ResearchResponse


def get_research(store: MemoryStoreInterface) -> ResearchResponse:
    records = store.list_recent(memory_type="semantic", limit=100)
    research_records = [
        record for record in records
        if "research" in record.tags or record.provenance.startswith("knowledge:")
    ]
    items = [
        ResearchNote(
            id=record.memory_id,
            title=record.content[:80] + ("…" if len(record.content) > 80 else ""),
            type="Experiment",
            date=f"Updated {record.created_at.isoformat()}",
        )
        for record in research_records
    ]
    return ResearchResponse(items=items, total=len(items))
