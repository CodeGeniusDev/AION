"""Schedule store: persistent SQLite-backed registry of scheduled desktop actions.

Mirrors ``memory/workflow_store.py`` — an interface contract with a real
SQLite implementation behind it and a safe ``CREATE TABLE IF NOT EXISTS``
migration. Rows survive restarts when ``AION_SCHEDULE_DB_PATH`` points at
a file; otherwise the store lives in in-memory SQLite for the process.

The store holds *intentions* only: which tool, with which parameters, on
what cadence. Firing is the runner's job, and a fire produces a PENDING
approval — never an execution. No demo rows are ever seeded.
"""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from models.schedules import Schedule, ScheduleStatus

DB_ROW_TIMEOUT = 5.0


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScheduleRecord(Schedule):
    """Stored row; identical to the public shape (nothing sensitive)."""


class ScheduleStoreInterface:
    def create(self, record: ScheduleRecord) -> ScheduleRecord: ...
    def get(self, schedule_id: str) -> ScheduleRecord | None: ...
    def list_all(self, tenant_id: str | None = None) -> list[ScheduleRecord]: ...
    def get_due(self, now_iso: str) -> list[ScheduleRecord]: ...
    def record_fire(
        self, schedule_id: str, *, approval_id: str,
        next_run_at: str | None, status: ScheduleStatus,
    ) -> ScheduleRecord | None: ...
    def set_status(
        self, schedule_id: str, status: ScheduleStatus, *, error: str | None = None,
    ) -> ScheduleRecord | None: ...
    def rearm(self, schedule_id: str, *, next_run_at: str) -> ScheduleRecord | None: ...


class SQLiteScheduleStore(ScheduleStoreInterface):
    _TABLE = "schedules"

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._connection = sqlite3.connect(
            db_path, check_same_thread=False, timeout=DB_ROW_TIMEOUT,
        )
        self._connection.row_factory = sqlite3.Row
        self._init_schema()

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
                    id               TEXT PRIMARY KEY,
                    name             TEXT NOT NULL,
                    tool             TEXT NOT NULL,
                    tenant_id        TEXT NOT NULL DEFAULT 'default',
                    parameters       TEXT NOT NULL DEFAULT '{{}}',
                    interval_seconds REAL NOT NULL DEFAULT 0,
                    status           TEXT NOT NULL DEFAULT 'active',
                    next_run_at      TEXT,
                    last_run_at      TEXT,
                    last_approval_id TEXT,
                    last_error       TEXT,
                    fire_count       INTEGER NOT NULL DEFAULT 0,
                    created_at       TEXT NOT NULL,
                    updated_at       TEXT NOT NULL
                )
            """)
            # Safe additive migration for DBs created before tenanting:
            # one column, never destructive, idempotent after first run.
            columns = {
                row[1]
                for row in cursor.execute(f"PRAGMA table_info({self._TABLE})")
            }
            if "tenant_id" not in columns:
                cursor.execute(
                    f"ALTER TABLE {self._TABLE} "
                    "ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'"
                )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, record: ScheduleRecord) -> ScheduleRecord:
        with self._cursor() as cursor:
            cursor.execute(
                f"""INSERT INTO {self._TABLE} (
                    id, name, tool, tenant_id, parameters, interval_seconds, status,
                    next_run_at, last_run_at, last_approval_id, last_error,
                    fire_count, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.id, record.name, record.tool, record.tenant_id,
                    json.dumps(record.parameters), record.interval_seconds,
                    record.status, record.next_run_at, record.last_run_at,
                    record.last_approval_id, record.last_error,
                    record.fire_count, record.created_at, record.updated_at,
                ),
            )
        return record

    def get(self, schedule_id: str) -> ScheduleRecord | None:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {self._TABLE} WHERE id = ?", (schedule_id,)
            )
            row = cursor.fetchone()
        return self._row_to_record(row) if row else None

    def list_all(self, tenant_id: str | None = None) -> list[ScheduleRecord]:
        with self._cursor() as cursor:
            if tenant_id is None:
                cursor.execute(
                    f"SELECT * FROM {self._TABLE} ORDER BY created_at ASC"
                )
            else:
                cursor.execute(
                    f"SELECT * FROM {self._TABLE} WHERE tenant_id = ? "
                    "ORDER BY created_at ASC",
                    (tenant_id,),
                )
            rows = cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_due(self, now_iso: str) -> list[ScheduleRecord]:
        """Active schedules whose clock time has arrived. ISO-8601 UTC
        strings sort lexicographically, so a plain comparison is sound."""
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {self._TABLE} "
                "WHERE status = 'active' AND next_run_at IS NOT NULL "
                "AND next_run_at <= ? "
                "ORDER BY next_run_at ASC",
                (now_iso,),
            )
            rows = cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    def record_fire(
        self, schedule_id: str, *, approval_id: str,
        next_run_at: str | None, status: ScheduleStatus,
    ) -> ScheduleRecord | None:
        """One fire accounted for: bump the counter, link the produced
        approval, and either re-arm (recurring) or finalize (one-shot)."""
        now = _utcnow()
        with self._cursor() as cursor:
            cursor.execute(
                f"UPDATE {self._TABLE} SET fire_count = fire_count + 1, "
                "last_run_at = ?, last_approval_id = ?, next_run_at = ?, "
                "status = ?, updated_at = ? WHERE id = ?",
                (now, approval_id, next_run_at, status, now, schedule_id),
            )
        return self.get(schedule_id)

    def set_status(
        self, schedule_id: str, status: ScheduleStatus, *, error: str | None = None,
    ) -> ScheduleRecord | None:
        now = _utcnow()
        with self._cursor() as cursor:
            if error is None:
                cursor.execute(
                    f"UPDATE {self._TABLE} SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now, schedule_id),
                )
            else:
                cursor.execute(
                    f"UPDATE {self._TABLE} SET status = ?, last_error = ?, "
                    "updated_at = ? WHERE id = ?",
                    (status, error[:500], now, schedule_id),
                )
        return self.get(schedule_id)

    def rearm(self, schedule_id: str, *, next_run_at: str) -> ScheduleRecord | None:
        """Resume semantics: active again, first fire one interval from
        now (never an instant burst for the time spent paused)."""
        now = _utcnow()
        with self._cursor() as cursor:
            cursor.execute(
                f"UPDATE {self._TABLE} SET status = 'active', next_run_at = ?, "
                "updated_at = ? WHERE id = ?",
                (next_run_at, now, schedule_id),
            )
        return self.get(schedule_id)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ScheduleRecord:
        return ScheduleRecord(
            id=row["id"],
            name=row["name"],
            tool=row["tool"],
            tenant_id=row["tenant_id"],
            parameters=json.loads(row["parameters"]),
            interval_seconds=row["interval_seconds"],
            status=row["status"],
            next_run_at=row["next_run_at"],
            last_run_at=row["last_run_at"],
            last_approval_id=row["last_approval_id"],
            last_error=row["last_error"],
            fire_count=row["fire_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def new_schedule(
    *, name: str, tool: str, parameters: dict, interval_seconds: float,
    delay_seconds: float = 0, now: datetime | None = None,
    tenant_id: str = "default",
) -> ScheduleRecord:
    """Build a fresh active schedule with its first fire armed
    ``delay_seconds`` from ``now`` (injectable clock)."""
    moment = now or datetime.now(timezone.utc)
    from datetime import timedelta

    return ScheduleRecord(
        id=f"sched-{uuid.uuid4().hex[:8]}",
        name=name,
        tool=tool,
        tenant_id=tenant_id,
        parameters=dict(parameters),
        interval_seconds=interval_seconds,
        status="active",
        next_run_at=(moment + timedelta(seconds=delay_seconds)).isoformat(),
        fire_count=0,
        created_at=moment.isoformat(),
        updated_at=moment.isoformat(),
    )


_default_store: SQLiteScheduleStore | None = None


def get_default_schedule_store() -> SQLiteScheduleStore:
    global _default_store
    if _default_store is None:
        from config import settings

        _default_store = SQLiteScheduleStore(settings.schedule_db_path or ":memory:")
    return _default_store


def reset_schedule_store() -> None:
    """Drop the cached singleton (used by tests)."""
    global _default_store
    if _default_store is not None:
        try:
            _default_store._connection.close()
        except Exception:
            pass
    _default_store = None
