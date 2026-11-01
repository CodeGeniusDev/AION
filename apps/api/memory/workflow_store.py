"""Workflow store: persistent SQLite-backed registry of reusable workflows.

Mirrors ``memory/task_store.py`` — a ``WorkflowStoreInterface`` contract with
a real SQLite implementation behind it. Workflows are named, ordered agent
paths that the API can run through the existing WorkflowRunner; ``runs`` is a
genuine execution counter and ``state`` reflects real in-flight executions
(nothing is faked).

Rows survive process restarts when ``AION_WORKFLOW_DB_PATH`` points at a
file; otherwise the store is an in-memory SQLite DB for the life of the
process. The three demo workflows are seeded once (empty table only) as real
rows — with real ``runs=0`` counters, not the fake demo numbers.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from models.workflows import Workflow, WorkflowState

DB_ROW_TIMEOUT = 5.0  # seconds to wait for a sqlite3 connection

# A "Running" row whose updated_at is older than this is considered stale
# (a crash between claim and finish) — reads report it as Ready and a new
# run may claim it. Covers the worst-case live Gemini pipeline duration.
RUNNING_STALE_SECONDS = 600


class WorkflowRecord(BaseModel):
    """Full stored row; ``to_public()`` produces the API-facing Workflow."""

    id: str
    name: str
    description: str
    agents: list[str] = Field(default_factory=list)  # display names (API shape)
    agent_ids: list[str] = Field(default_factory=list)  # canonical model-safe AgentIds
    runs: int = 0
    state: WorkflowState = "Ready"
    last_task_id: str | None = None
    last_error: str | None = None
    created_at: str
    updated_at: str

    def to_public(self, *, effective_state: WorkflowState | None = None) -> Workflow:
        return Workflow(
            id=self.id,
            name=self.name,
            description=self.description,
            agents=list(self.agents),
            runs=self.runs,
            state=effective_state or self.state,
        )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_stale(updated_at: str) -> bool:
    try:
        ts = datetime.fromisoformat(updated_at)
    except ValueError:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ts > timedelta(seconds=RUNNING_STALE_SECONDS)


# The three demo workflows, seeded once as real rows. agent_ids are the
# canonical model-safe chat AgentIds; agents preserves the exact display
# names the previous demo response used (frontend contract unchanged).
SEED_WORKFLOWS: list[dict] = [
    {
        "id": "deep-research",
        "name": "Deep Research",
        "description": "Investigate a question, challenge the findings, and save the useful context.",
        "agents": ["Planner", "Research", "Critic", "Memory"],
        "agent_ids": ["planner", "researcher", "critic", "memory"],
    },
    {
        "id": "decision-brief",
        "name": "Decision Brief",
        "description": "Turn complex inputs into a focused recommendation with reviewed evidence.",
        "agents": ["Research", "Critic", "Planner"],
        "agent_ids": ["researcher", "critic", "planner"],
    },
    {
        "id": "knowledge-capture",
        "name": "Knowledge Capture",
        "description": "Structure new information and route it into the appropriate memory layer.",
        "agents": ["Memory", "Critic"],
        "agent_ids": ["memory", "critic"],
    },
]


class WorkflowStoreInterface:
    """Storage-agnostic contract for workflow persistence."""

    def create(self, record: WorkflowRecord) -> WorkflowRecord: ...

    def get(self, workflow_id: str) -> WorkflowRecord | None: ...

    def list_all(self) -> list[WorkflowRecord]: ...

    def claim_for_run(self, workflow_id: str) -> WorkflowRecord | None: ...

    def finish_run(
        self, workflow_id: str, *, last_task_id: str | None = None, error: str | None = None,
    ) -> WorkflowRecord | None: ...


class SQLiteWorkflowStore(WorkflowStoreInterface):
    _TABLE = "workflows"

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        # One long-lived connection (":memory:" gives each connection its own
        # isolated DB). check_same_thread=False so any worker may call it.
        self._connection = sqlite3.connect(
            db_path, check_same_thread=False, timeout=DB_ROW_TIMEOUT,
        )
        self._connection.row_factory = sqlite3.Row
        self._init_schema()
        self._seed_once()

    @contextmanager
    def _cursor(self):
        cursor = self._connection.cursor()
        try:
            yield cursor
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def _init_schema(self) -> None:
        with self._cursor() as cursor:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._TABLE} (
                    id            TEXT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    description   TEXT NOT NULL DEFAULT '',
                    agents_json   TEXT NOT NULL DEFAULT '[]',
                    agent_ids_json TEXT NOT NULL DEFAULT '[]',
                    runs          INTEGER NOT NULL DEFAULT 0 CHECK(runs >= 0),
                    state         TEXT NOT NULL DEFAULT 'Ready'
                                 CHECK(state IN ('Ready', 'Running')),
                    last_task_id  TEXT,
                    last_error    TEXT,
                    created_at    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL
                )
            """)

    def _seed_once(self) -> None:
        """Insert the 3 demo workflows only when the table is empty, so a
        restart never duplicates or resurrects deleted rows."""
        with self._cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS n FROM {self._TABLE}")
            if cursor.fetchone()["n"] > 0:
                return
            now = _utcnow()
            for seed in SEED_WORKFLOWS:
                cursor.execute(
                    f"INSERT INTO {self._TABLE} (id, name, description, agents_json, "
                    "agent_ids_json, runs, state, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 0, 'Ready', ?, ?)",
                    (
                        seed["id"], seed["name"], seed["description"],
                        json.dumps(seed["agents"]), json.dumps(seed["agent_ids"]),
                        now, now,
                    ),
                )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, workflow_id: str) -> WorkflowRecord | None:
        with self._cursor() as cursor:
            cursor.execute(f"SELECT * FROM {self._TABLE} WHERE id = ?", (workflow_id,))
            row = cursor.fetchone()
        return self._row_to_record(row) if row else None

    def list_all(self) -> list[WorkflowRecord]:
        with self._cursor() as cursor:
            cursor.execute(f"SELECT * FROM {self._TABLE} ORDER BY created_at, id")
            rows = cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    def public_list(self) -> list[Workflow]:
        """API-facing list with the stale-Running correction applied."""
        result: list[Workflow] = []
        for record in self.list_all():
            effective = self._effective_state(record)
            result.append(record.to_public(effective_state=effective))
        return result

    def public_get(self, workflow_id: str) -> Workflow | None:
        record = self.get(workflow_id)
        if record is None:
            return None
        return record.to_public(effective_state=self._effective_state(record))

    @staticmethod
    def _effective_state(record: WorkflowRecord) -> WorkflowState:
        if record.state == "Running" and _is_stale(record.updated_at):
            return "Ready"
        return record.state

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create(self, record: WorkflowRecord) -> WorkflowRecord:
        with self._cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {self._TABLE} (id, name, description, agents_json, "
                "agent_ids_json, runs, state, last_task_id, last_error, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id, record.name, record.description,
                    json.dumps(record.agents), json.dumps(record.agent_ids),
                    record.runs, record.state, record.last_task_id, record.last_error,
                    record.created_at, record.updated_at,
                ),
            )
        stored = self.get(record.id)
        assert stored is not None
        return stored

    def claim_for_run(self, workflow_id: str) -> WorkflowRecord | None:
        """Atomically mark a workflow Running and increment its run counter.

        The conditional UPDATE is the guard: a workflow that is genuinely
        Running (fresh updated_at) can never be claimed twice, so two
        concurrent run requests can't both execute. Returns the claimed
        record, or None if it doesn't exist / is already running.
        """
        now = _utcnow()
        stale_cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=RUNNING_STALE_SECONDS)
        ).isoformat()
        with self._cursor() as cursor:
            cursor.execute(
                f"UPDATE {self._TABLE} SET state = 'Running', runs = runs + 1, updated_at = ? "
                "WHERE id = ? AND (state <> 'Running' OR updated_at < ?)",
                (now, workflow_id, stale_cutoff),
            )
            claimed = cursor.rowcount == 1
        if not claimed:
            return None
        record = self.get(workflow_id)
        assert record is not None
        return record

    def finish_run(
        self, workflow_id: str, *, last_task_id: str | None = None, error: str | None = None,
    ) -> WorkflowRecord | None:
        with self._cursor() as cursor:
            cursor.execute(
                f"UPDATE {self._TABLE} SET state = 'Ready', last_task_id = COALESCE(?, last_task_id), "
                "last_error = ?, updated_at = ? WHERE id = ?",
                (last_task_id, error, _utcnow(), workflow_id),
            )
        return self.get(workflow_id)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> WorkflowRecord:
        return WorkflowRecord(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            agents=json.loads(row["agents_json"]),
            agent_ids=json.loads(row["agent_ids_json"]),
            runs=row["runs"],
            state=row["state"],
            last_task_id=row["last_task_id"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


_default_store: SQLiteWorkflowStore | None = None


def get_default_workflow_store() -> SQLiteWorkflowStore:
    """Process-wide store wired from settings (mirrors task store pattern)."""
    global _default_store
    if _default_store is None:
        from config import settings

        _default_store = SQLiteWorkflowStore(settings.workflow_db_path or ":memory:")
    return _default_store


def reset_workflow_store() -> None:
    """Drop the cached singleton (used by tests)."""
    global _default_store
    if _default_store is not None:
        try:
            _default_store._connection.close()
        except Exception:
            pass
    _default_store = None
