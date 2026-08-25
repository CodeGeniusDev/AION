"""Cognitive Memory: real, persistent, provenance-aware storage.

SQLiteMemoryStore (store.py) is the active implementation — genuine SQL
persistence today, not a placeholder. PgVectorMemory (pgvector.py) remains
an explicit placeholder for a future embedding-similarity backend
implementing the same MemoryStoreInterface.
"""

from memory.store import MemoryStoreInterface, SQLiteMemoryStore

__all__ = ["MemoryStoreInterface", "SQLiteMemoryStore"]
