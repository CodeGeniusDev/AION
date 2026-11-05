"""Task store: persistent SQLite-backed task registry for the AION Desktop OS MVP.

This mirrors the pattern of ``memory/store.py`` — a real, persistent SQLite
storage behind a ``TaskStoreInterface``. Tasks are the unit of work in the
desktop agent and social scheduler: each tool call, browser action, or
scheduled post gets its own task record with a status
(``pending`` → ``running`` → ``completed``/``failed``).

Tasks are durable: they survive process restarts via the SQLite file
(provided the user points ``AION_MEMORY_DB_PATH`` at a real file, as the
Docker Compose deployment does).
"""

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.tasks import Task, TaskStatus, TasksResponse
from models.tool import ToolOutput

DB_ROW_TIMEOUT = 5.0  # seconds to wait for a sqlite3 connection


class TaskStoreInterface(ABC):
    """Storage-agnostic contract for task persistence."""

    @abstractmethod
    def create(self, task: Task) -> Task:
        """Insert a new task and return the stored record."""

    @abstractmethod
    def get(self, task_id: str) -> Task | None:
        """Fetch a single task by id."""

    @abstractmethod
    def list_all(self, status: TaskStatus | None = None) -> list[Task]:
        """Fetch all tasks, optionally filtered by status."""

    @abstractmethod
    def update_status(self, task_id: str, status: TaskStatus) -> Task | None:
        """Update a task's status and return the stored record."""

    @abstractmethod
    def update_output(self, task_id: str, output: ToolOutput) -> Task | None:
        """Attach a tool output to a task and return the stored record."""

    @abstractmethod
    def delete(self, task_id: str) -> bool:
        """Delete a task. Returns True if a row was removed."""


class SQLiteTaskStore(TaskStoreInterface):
    """Real persistent storage. SQLite file-backed for durability."""

    _TABLE = "tasks"
    _INDEX = "idx_tasks_status"

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._connection: sqlite3.Connection | None = None
        # A single long-lived connection is required for ":memory:" (each
        # connection gets its own isolated DB). Use check_same_thread=False
        # so the store can be called from any thread.
        self._connection = sqlite3.connect(
            db_path, check_same_thread=False, timeout=DB_ROW_TIMEOUT,
        )
        self._connection.row_factory = sqlite3.Row
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=DB_ROW_TIMEOUT,
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    @contextmanager
    def _cursor(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_schema(self) -> None:
        with self._cursor() as cursor:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._TABLE} (
                    id            TEXT PRIMARY KEY,
                    title         TEXT NOT NULL,
                    agent         TEXT NOT NULL DEFAULT 'aion',
                    status        TEXT NOT NULL DEFAULT 'pending'
                                 CHECK(status IN ('pending', 'pending_approval', 'running', 'completed', 'failed')),
                    confidence    INTEGER NOT NULL DEFAULT 0,
                    created       TEXT NOT NULL,
                    output        TEXT,
                    updated       TEXT NOT NULL
                )
            """)
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS {self._INDEX}
                ON {self._TABLE} (status)
            """)
        # Check if migration is needed (old schema without CHECK constraint)
        if self._needs_migration():
            self._migrate()

    def _needs_migration(self) -> bool:
        """Check if the existing DB schema needs migration to add CHECK constraint."""
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (self._TABLE,)
            )
            row = cursor.fetchone()
            if row is None:
                return False
            schema = row[0] or ""
            # Check if CHECK constraint is present
            return "CHECK(status" not in schema

    def _migrate(self) -> None:
        """Migrate an old-schema DB (without CHECK constraint) to the new schema."""
        with self._cursor() as cursor:
            # Backup the old table data
            cursor.execute(f"ALTER TABLE {self._TABLE} RENAME TO {self._TABLE}_backup")
            # Drop the old table and recreate with new schema (now covered by _init_schema)
            cursor.execute(f"DROP TABLE IF EXISTS {self._TABLE}")
            # Recreate the table with new schema (this includes CHECK constraint)
            self._init_schema()
            # Copy existing data back
            cursor.execute(f"SELECT * FROM {self._TABLE}_backup")
            rows = cursor.fetchall()
            for row in rows:
                cursor.execute(
                    f"INSERT INTO {self._TABLE} (id, title, agent, status, confidence, created, output, updated) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row["id"], row["title"], row["agent"], row["status"],
                        row["confidence"], row["created"], row["output"], row["updated"],
                    ),
                )
            # Drop backup table if it exists
            cursor.execute(f"DROP TABLE IF EXISTS {self._TABLE}_backup")

    def create(self, task: Task) -> Task:
        now = datetime.now(timezone.utc).isoformat()
        with self._cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {self._TABLE}
                    (id, title, agent, status, confidence, created, updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.title,
                    task.agent,
                    task.status,
                    task.confidence,
                    task.created or now,
                    now,
                ),
            )
        return self.get(task.id) or task

    def get(self, task_id: str) -> Task | None:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {self._TABLE} WHERE id = ?", (task_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    def list_all(self, status: TaskStatus | None = None) -> list[Task]:
        with self._cursor() as cursor:
            if status is None:
                cursor.execute(f"SELECT * FROM {self._TABLE} ORDER BY created DESC")
            else:
                cursor.execute(
                    f"SELECT * FROM {self._TABLE} WHERE status = ? ORDER BY created DESC",
                    (status,),
                )
            rows = cursor.fetchall()
        return [self._row_to_task(row) for row in rows]

    def update_status(self, task_id: str, status: TaskStatus) -> Task | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {self._TABLE}
                SET status = ?, updated = ?
                WHERE id = ?
                """,
                (status, now, task_id),
            )
        result = self.get(task_id)
        # Phase 2B: notify SSE subscribers of task status change.
        if result is not None:
            try:
                from realtime.publishers import publish_task_updated
                from config import settings as _settings
                publish_task_updated(_settings.default_tenant_id, task_id=task_id, status=result.status)
            except Exception:
                pass
        return result

    def update_output(self, task_id: str, output: ToolOutput) -> Task | None:
        now = datetime.now(timezone.utc).isoformat()
        serialized = json.dumps(output.model_dump(mode="json"))
        with self._cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {self._TABLE}
                SET output = ?, updated = ?
                WHERE id = ?
                """,
                (serialized, now, task_id),
            )
        return self.get(task_id)

    def delete(self, task_id: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {self._TABLE} WHERE id = ?", (task_id,),
            )
            return cursor.rowcount > 0

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        output = None
        if row["output"]:
            try:
                output = ToolOutput.model_validate_json(row["output"])
            except Exception:
                output = None
        return Task(
            id=row["id"],
            title=row["title"],
            agent=row["agent"],
            status=row["status"],
            confidence=row["confidence"],
            created=row["created"],
            output=output,
            updated=row["updated"],
        )


# Singleton instance. The local agent should create its own store with a
# real file path; the WorkflowRunner and routes use this singleton.
default_task_store: SQLiteTaskStore | None = None


def get_default_task_store() -> SQLiteTaskStore:
    global default_task_store
    if default_task_store is None:
        default_task_store = SQLiteTaskStore()
    return default_task_store


def reset_task_store() -> None:
    global default_task_store
    default_task_store = None
