"""Memory API service.

Sources real counts from the live Cognitive Memory store used by
/api/chat (routes/chat.py's `workflow_runner.memory_store`) — the actual
SQLite-backed store, not a separate/duplicate data source. Category
titles/descriptions and the "usage" percentage remain presentational
(there is no real capacity ceiling to compute a genuine utilization
percentage against — SQLite has no fixed quota here), but the item counts
are real, measured values from the live database, not invented numbers.
"""

from memory.store import MemoryStoreInterface
from models.memory import MemoryCategory, MemoryResponse

_POLICIES: list[str] = [
    "Only Immune-verified claims become long-term semantic memory",
    "Contradicted or unsupported claims are never persisted",
    "Every record carries task/agent provenance",
]

_CATEGORY_META = {
    "episodic": ("Episodic Memory", "A log of what AION did for each completed task."),
    "semantic": ("Semantic Memory", "Reusable facts, verified by the Immune System before being stored."),
    "task_context": ("Task Context", "Short-lived working memory supplied per request."),
}

# The frontend's 3-bucket display scheme (short_term/long_term/vector,
# models/memory.py) predates and doesn't perfectly correspond to the real
# 3 Cognitive Memory types above. Mapped as honestly as the fixed 3-bucket
# schema allows: episodic (task-bound log) -> short_term, semantic
# (durable, reusable) -> long_term. task_context has no good match in
# either "short_term" or "long_term" conceptually and is mapped to
# "vector" only because it's the remaining bucket — this is a cosmetic
# grouping label, not a claim that task_context uses vector storage.
_DISPLAY_TYPE = {"episodic": "short_term", "semantic": "long_term", "task_context": "vector"}


def get_memory(store: MemoryStoreInterface) -> MemoryResponse:
    """Real category counts from the live memory store passed in by the
    caller (routes/memory.py — sourced from the same singleton /api/chat
    writes to)."""
    categories = []
    for memory_type, (title, description) in _CATEGORY_META.items():
        records = store.list_recent(memory_type=memory_type, limit=1000)
        count = len(records)
        categories.append(MemoryCategory(
            id=memory_type,
            title=title,
            description=description,
            type=_DISPLAY_TYPE[memory_type],
            count=f"{count} record{'s' if count != 1 else ''}",
            usage=min(100, count * 4),  # presentational only — no real capacity ceiling exists to measure utilization against
        ))
    return MemoryResponse(categories=categories, policies=_POLICIES)
