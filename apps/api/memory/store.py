"""Cognitive Memory storage: a real, persistent SQLite-backed store behind a
storage-agnostic interface.

Why SQLite and not Postgres/pgvector right now: `DATABASE_URL` in this
codebase is declared but has never been consumed anywhere — there is no
provisioned Postgres instance to connect to. SQLite is Python's standard
library, requires no new dependency, and gives genuine ACID-compliant
persistent SQL storage today rather than another placeholder. Swapping to
Postgres/pgvector later means writing a new class that implements
`MemoryStoreInterface` — no caller (WorkflowRunner, MemoryAgent, retrieval)
needs to change, because they only depend on the interface.

Relevance scoring: no embedding provider is active by default (see
memory/embeddings.py), so `search()` falls back to a deterministic lexical
word-overlap score. This is documented as a heuristic, not semantic
understanding — see MemorySearchResult.relevance_score's docstring. If an
EmbeddingProvider that returns real vectors is supplied, `search()` uses
cosine similarity over those vectors instead — but nothing here fabricates
an embedding when none is configured.
"""

import json
import re
import sqlite3
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime

from memory.embeddings import EmbeddingProvider, NullEmbeddingProvider
from models.cognitive_memory import MemoryRecord, MemorySearchResult, MemoryType

_WORD_PATTERN = re.compile(r"[a-zA-Z]+")


def _keywords(text: str) -> set[str]:
    return {word.lower() for word in _WORD_PATTERN.findall(text) if len(word) > 3}


def _lexical_relevance(query: str, content: str) -> float:
    query_words = _keywords(query)
    content_words = _keywords(content)
    if not query_words or not content_words:
        return 0.0
    return len(query_words & content_words) / len(query_words | content_words)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


class MemoryStoreInterface(ABC):
    """Storage-agnostic contract. Every caller in AION depends on this, not
    on SQLiteMemoryStore's implementation details."""

    @abstractmethod
    def write(self, record: MemoryRecord) -> MemoryRecord: ...

    @abstractmethod
    def get(self, memory_id: str) -> MemoryRecord | None: ...

    @abstractmethod
    def list_for_task(self, task_id: str) -> list[MemoryRecord]: ...

    @abstractmethod
    def search(
        self, *, query: str, memory_type: MemoryType | None = None,
        tags: list[str] | None = None, limit: int = 5, tenant_id: str | None = None,
    ) -> list[MemorySearchResult]: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def list_recent(
        self, *, memory_type: MemoryType | None = None, tenant_id: str | None = None, limit: int = 20,
    ) -> list[MemoryRecord]:
        """Most recently written records, newest first. Unlike search(),
        this requires no query text — used by API routes that want to show
        real recent activity (e.g. a dashboard or task list) rather than a
        relevance-ranked result set."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all records. Administrative/test use only."""


class SQLiteMemoryStore(MemoryStoreInterface):
    """Real persistent storage. `db_path=":memory:"` gives an isolated,
    real (not fake) SQLite database that lives for the connection's
    lifetime — used as WorkflowRunner's process-lifetime default (see its
    docstring for why). Pass a real file path for durability across process
    restarts; the interface and behavior are identical either way.
    """

    def __init__(self, db_path: str = ":memory:", *, embedding_provider: EmbeddingProvider | None = None) -> None:
        self.db_path = db_path
        self.embedding_provider = embedding_provider or NullEmbeddingProvider()
        # A single long-lived connection is required for ":memory:" (each
        # new connection to ":memory:" would otherwise be a distinct, empty
        # database) and is also used for a file path in this single-process
        # deployment. `check_same_thread=False` only disables Python's
        # same-thread safety CHECK — per the sqlite3 documentation, it does
        # NOT make concurrent use of one Connection object across threads
        # actually safe. Since WorkflowRunner offloads store calls via
        # `asyncio.to_thread()` (to keep the event loop non-blocking — see
        # orchestration/workflow_runner.py), concurrent requests can genuinely
        # dispatch to different threadpool threads that would otherwise touch
        # this connection simultaneously. `self._lock` serializes only the
        # actual (fast, microsecond-scale) SQL execution — the event loop
        # itself is never blocked by it, since to_thread() has already
        # handed control back before the lock is acquired. This is
        # deliberately NOT full serialization of request handling, only of
        # the one genuinely shared, non-thread-safe resource.
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    source_agent TEXT NOT NULL,
                    verification_state TEXT NOT NULL,
                    confidence REAL,
                    tags TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    tenant_id TEXT,
                    created_at TEXT NOT NULL,
                    embedding TEXT
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_task_id ON memories(task_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_tenant_id ON memories(tenant_id)")

    @contextmanager
    def _cursor(self):
        with self._lock:
            cursor = self._connection.cursor()
            try:
                yield cursor
                self._connection.commit()
            finally:
                cursor.close()

    def write(self, record: MemoryRecord) -> MemoryRecord:
        embedding = self.embedding_provider.embed(record.content)
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO memories
                    (memory_id, type, content, task_id, source_agent, verification_state,
                     confidence, tags, provenance, tenant_id, created_at, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.memory_id, record.type, record.content, record.task_id, record.source_agent,
                    record.verification_state, record.confidence, json.dumps(record.tags), record.provenance,
                    record.tenant_id, record.created_at.isoformat(), json.dumps(embedding) if embedding is not None else None,
                ),
            )
        return record

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM memories WHERE memory_id = ?", (memory_id,))
            row = cursor.fetchone()
        return self._row_to_record(row) if row else None

    def list_for_task(self, task_id: str) -> list[MemoryRecord]:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM memories WHERE task_id = ? ORDER BY created_at ASC", (task_id,))
            rows = cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    def search(
        self, *, query: str, memory_type: MemoryType | None = None,
        tags: list[str] | None = None, limit: int = 5, tenant_id: str | None = None,
    ) -> list[MemorySearchResult]:
        """Tenant isolation: when `tenant_id` is given, ONLY that tenant's
        own records are eligible — untenanted (tenant_id=None) records are
        NOT included as a fallback. This is strict by design: a caller
        asking "search within my tenant" must never silently see shared or
        another tenant's data. Omitting `tenant_id` entirely (None) means
        "no tenant filter" — the pre-existing, backward-compatible global
        search behavior used by every caller written before authentication
        existed.
        """
        sql = "SELECT * FROM memories WHERE 1=1"
        params: list[object] = []
        if memory_type is not None:
            sql += " AND type = ?"
            params.append(memory_type)
        if tenant_id is not None:
            sql += " AND tenant_id = ?"
            params.append(tenant_id)
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        query_embedding = self.embedding_provider.embed(query)
        results: list[MemorySearchResult] = []
        for row in rows:
            record = self._row_to_record(row)
            if tags and not (set(tags) & set(record.tags)):
                continue

            stored_embedding = json.loads(row["embedding"]) if row["embedding"] else None
            if query_embedding is not None and stored_embedding is not None:
                score = _cosine_similarity(query_embedding, stored_embedding)
            else:
                score = _lexical_relevance(query, record.content)

            if score > 0.0:
                results.append(MemorySearchResult(record=record, relevance_score=round(score, 4)))

        results.sort(key=lambda result: result.relevance_score, reverse=True)
        return results[:limit]

    def count(self) -> int:
        with self._cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM memories")
            return cursor.fetchone()["n"]

    def list_recent(
        self, *, memory_type: MemoryType | None = None, tenant_id: str | None = None, limit: int = 20,
    ) -> list[MemoryRecord]:
        sql = "SELECT * FROM memories WHERE 1=1"
        params: list[object] = []
        if memory_type is not None:
            sql += " AND type = ?"
            params.append(memory_type)
        if tenant_id is not None:
            sql += " AND tenant_id = ?"
            params.append(tenant_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    def clear(self) -> None:
        with self._cursor() as cursor:
            cursor.execute("DELETE FROM memories")

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["memory_id"], type=row["type"], content=row["content"],
            task_id=row["task_id"], source_agent=row["source_agent"],
            verification_state=row["verification_state"], confidence=row["confidence"],
            tags=json.loads(row["tags"]), provenance=row["provenance"], tenant_id=row["tenant_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
