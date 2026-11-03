"""Persistent profile + workspace-settings store — SQLite-backed.

Single-tenant: the profile table holds at most one row (id = 1) and is
NEVER seeded — an empty table is the honest "first run" state the UI
renders as "Set up profile".

Settings persistence reuses the same database (key-value table) so
PUT /api/settings survives restarts without adding a second file.

Thread safety follows memory/alert_store.py: one connection with
`check_same_thread=False` plus a lock serializing SQL.
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

_PROFILE_ID = 1


class ProfileStore:
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
                CREATE TABLE IF NOT EXISTS profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    display_name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    email TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT '',
                    timezone TEXT NOT NULL DEFAULT 'UTC',
                    bio TEXT NOT NULL DEFAULT '',
                    avatar_color TEXT NOT NULL DEFAULT 'navy',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    @contextmanager
    def _cursor(self):
        with self._lock:
            cursor = self._connection.cursor()
            try:
                yield cursor
                self._connection.commit()
            finally:
                cursor.close()

    # ------------------------------------------------------------------
    # Profile (single row, never seeded)
    # ------------------------------------------------------------------

    def get_profile(self) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM profile WHERE id = ?", (_PROFILE_ID,))
            row = cursor.fetchone()
        return dict(row) if row else None

    def upsert_profile(self, data: dict) -> dict:
        """Insert or replace the profile row. created_at survives updates."""
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get_profile()
        created_at = existing["created_at"] if existing else now
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO profile (id, display_name, username, email, role,
                                     timezone, bio, avatar_color, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    display_name=excluded.display_name,
                    username=excluded.username,
                    email=excluded.email,
                    role=excluded.role,
                    timezone=excluded.timezone,
                    bio=excluded.bio,
                    avatar_color=excluded.avatar_color,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at
                """,
                (
                    _PROFILE_ID,
                    data["display_name"], data["username"], data["email"],
                    data["role"], data["timezone"], data["bio"],
                    data["avatar_color"], created_at, now,
                ),
            )
        row = self.get_profile()
        assert row is not None
        return row

    # ------------------------------------------------------------------
    # Workspace settings (persisted JSON, same database)
    # ------------------------------------------------------------------

    def get_settings_json(self) -> str | None:
        with self._cursor() as cursor:
            cursor.execute("SELECT value FROM settings WHERE key = 'app_settings'")
            row = cursor.fetchone()
        return row["value"] if row else None

    def set_settings_json(self, value: str) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES ('app_settings', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (value,),
            )


_default_store: ProfileStore | None = None


def get_default_profile_store() -> ProfileStore:
    """Process-wide store. Path: AION_PROFILE_DB_PATH, else the git-ignored
    apps/api/.data/profile.db (created on demand)."""
    global _default_store
    if _default_store is None:
        from config import settings

        if settings.profile_db_path:
            path = settings.profile_db_path
        else:
            from pathlib import Path

            data_dir = Path(__file__).resolve().parents[1] / ".data"
            data_dir.mkdir(exist_ok=True)
            path = str(data_dir / "profile.db")
        _default_store = ProfileStore(path)
    return _default_store


def reset_default_profile_store() -> None:
    """Drop the cached instance (tests point the env var at a temp file)."""
    global _default_store
    _default_store = None
