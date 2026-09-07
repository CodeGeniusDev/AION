"""Persistent notification store — SQLite-backed.

Generates and persists alerts from system events (task completions,
failures, agent activity). Alerts survive page refresh and server
restarts when backed by a file-path SQLite database.

Thread safety follows the same pattern as SQLiteMemoryStore: a single
connection with `check_same_thread=False` and a lock serializing SQL
execution (see memory/store.py for the rationale).
"""

import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone


class AlertStore:
    """SQLite-backed alert persistence.

    `db_path=":memory:"` gives a process-lifetime store (used as the
    default when no file path is configured). Pass a real file path
    for durability across restarts.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    time TEXT NOT NULL,
                    category TEXT NOT NULL,
                    unread INTEGER NOT NULL DEFAULT 1,
                    tone TEXT NOT NULL DEFAULT 'info',
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_unread ON alerts(unread)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at)")

    @contextmanager
    def _cursor(self):
        with self._lock:
            cursor = self._connection.cursor()
            try:
                yield cursor
                self._connection.commit()
            finally:
                cursor.close()

    def create(
        self, *, title: str, description: str, category: str = "system",
        tone: str = "info",
    ) -> dict:
        """Create a new alert. Returns the created alert as a dict."""
        now = datetime.now(timezone.utc)
        alert_id = f"alert-{uuid.uuid4().hex[:12]}"
        time_str = _relative_time(now)
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO alerts (id, title, description, time, category, unread, tone, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (alert_id, title, description, time_str, category, tone, now.isoformat()),
            )
        return {
            "id": alert_id, "title": title, "description": description,
            "time": time_str, "category": category, "unread": True, "tone": tone,
        }

    def list_all(self, *, unread_only: bool = False, limit: int = 50) -> list[dict]:
        """List alerts, newest first."""
        sql = "SELECT * FROM alerts"
        if unread_only:
            sql += " WHERE unread = 1"
        sql += " ORDER BY created_at DESC LIMIT ?"
        with self._cursor() as cursor:
            cursor.execute(sql, (limit,))
            rows = cursor.fetchall()
        return [_row_to_dict(row) for row in rows]

    def count_unread(self) -> int:
        with self._cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM alerts WHERE unread = 1")
            return cursor.fetchone()["n"]

    def mark_read(self, alert_ids: list[str]) -> int:
        """Mark specific alerts as read. Returns count of actually updated rows."""
        if not alert_ids:
            return 0
        placeholders = ",".join("?" for _ in alert_ids)
        with self._cursor() as cursor:
            cursor.execute(
                f"UPDATE alerts SET unread = 0 WHERE id IN ({placeholders})",
                alert_ids,
            )
            return cursor.rowcount

    def mark_all_read(self) -> int:
        """Mark all alerts as read. Returns count of updated rows."""
        with self._cursor() as cursor:
            cursor.execute("UPDATE alerts SET unread = 0 WHERE unread = 1")
            return cursor.rowcount

    def delete(self, alert_id: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
            return cursor.rowcount > 0

    def create_task_alert(self, *, task_id: str, message_preview: str, status: str) -> dict:
        """Auto-generate an alert from a chat task completion or failure."""
        if status == "completed":
            title = "Task completed"
            description = f'AION completed: "{message_preview[:80]}"'
            tone = "success"
        else:
            title = "Task failed"
            description = f'AION could not complete: "{message_preview[:80]}"'
            tone = "error"
        return self.create(title=title, description=description, category="task", tone=tone)


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "time": row["time"],
        "category": row["category"],
        "unread": bool(row["unread"]),
        "tone": row["tone"],
    }


def _relative_time(dt: datetime) -> str:
    """Format a datetime as a human-readable relative string."""
    return dt.strftime("%b %d, %Y · %I:%M %p")
