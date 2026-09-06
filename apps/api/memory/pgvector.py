"""Placeholder for a future pgvector-backed semantic memory implementation.

The active memory backend today is SQLiteMemoryStore (see store.py),
implementing MemoryStoreInterface with real lexical-relevance search. A
future PgVectorMemory would implement the same MemoryStoreInterface —
callers (WorkflowRunner, retrieval, consolidation) would not need to
change.
"""


class PgVectorMemory:
    """Placeholder for future pgvector-backed semantic memory."""

    def search(self, query: str) -> list[str]:
        _ = query
        return []
