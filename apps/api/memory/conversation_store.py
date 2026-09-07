"""Conversation persistence: stores chat messages keyed by conversation_id.

SQLite-backed, same architecture as memory/store.py. Default is in-memory
(process-lifetime); pass a file path for durability across restarts.
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class StoredMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg-{uuid4().hex[:10]}")
    conversation_id: str
    role: str  # "user" or "assistant"
    content: str
    task_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    message_count: int
    last_message_at: str
    created_at: str


class ConversationStore:
    def __init__(self, db_path: str = ":memory:") -> None:
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    task_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_convo ON messages(conversation_id)")

    @contextmanager
    def _cursor(self):
        with self._lock:
            cursor = self._connection.cursor()
            try:
                yield cursor
                self._connection.commit()
            finally:
                cursor.close()

    def save_user_message(self, conversation_id: str, content: str, *, title: str | None = None) -> StoredMessage:
        """Save a user message, creating the conversation if needed."""
        now = datetime.now(timezone.utc)
        # Generate a clean title from the first message
        if not title:
            title = content.strip()[:60]
            if len(content.strip()) > 60:
                title += "..."
        with self._cursor() as cursor:
            # Upsert conversation
            cursor.execute(
                "INSERT INTO conversations (conversation_id, title, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(conversation_id) DO NOTHING",
                (conversation_id, title, now.isoformat()),
            )
            msg = StoredMessage(conversation_id=conversation_id, role="user", content=content, created_at=now)
            cursor.execute(
                "INSERT INTO messages (message_id, conversation_id, role, content, task_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (msg.message_id, conversation_id, "user", content, None, now.isoformat()),
            )
        return msg

    def save_assistant_message(self, conversation_id: str, content: str, *, task_id: str) -> StoredMessage:
        """Save an assistant (AION) response."""
        now = datetime.now(timezone.utc)
        msg = StoredMessage(conversation_id=conversation_id, role="assistant", content=content, task_id=task_id, created_at=now)
        with self._cursor() as cursor:
            cursor.execute(
                "INSERT INTO messages (message_id, conversation_id, role, content, task_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (msg.message_id, conversation_id, "assistant", content, task_id, now.isoformat()),
            )
        return msg

    def get_messages(self, conversation_id: str) -> list[StoredMessage]:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            )
            rows = cursor.fetchall()
        return [
            StoredMessage(
                message_id=row["message_id"], conversation_id=row["conversation_id"],
                role=row["role"], content=row["content"], task_id=row["task_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def list_conversations(self, *, limit: int = 20) -> list[ConversationSummary]:
        with self._cursor() as cursor:
            cursor.execute("""
                SELECT c.conversation_id, c.title, c.created_at,
                       COUNT(m.message_id) AS message_count,
                       MAX(m.created_at) AS last_message_at
                FROM conversations c
                LEFT JOIN messages m ON c.conversation_id = m.conversation_id
                GROUP BY c.conversation_id
                ORDER BY COALESCE(MAX(m.created_at), c.created_at) DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
        return [
            ConversationSummary(
                conversation_id=row["conversation_id"],
                title=row["title"],
                message_count=row["message_count"],
                last_message_at=row["last_message_at"] or row["created_at"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            cursor.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
            return cursor.rowcount > 0
