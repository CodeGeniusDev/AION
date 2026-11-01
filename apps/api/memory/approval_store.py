"""Approval ledger: persistent SQLite-backed store for the human-in-the-loop
desktop tool approval lifecycle, plus an append-only execution audit log.

Mirrors the connection pattern of ``memory/task_store.py`` (single
long-lived connection, ``check_same_thread=False``) with the SQL
serialization lock of ``memory/alert_store.py`` — every transition is a
conditional ``UPDATE ... WHERE id=? AND status=?`` whose ``rowcount`` the
caller must check. The "an approved action runs exactly once" property
comes from this atomic claim semantics, not from client behavior.

Lifecycle (per row):

    pending_approval ──approve+claim (one step)──► running ──► completed
                                                        ╲────► failed
    pending_approval ──reject──► rejected   (terminal, never executes)
    pending_approval ──deadline──► expired  (terminal, late approve refused)

The audit_log table is append-only by construction: this class exposes
``audit()`` and ``list_audit()`` only — there is no UPDATE or DELETE path.
Raw one-time grant tokens are never stored anywhere; only their SHA-256
hashes (so a bridge grant can be correlated with a ledger row without the
DB being usable to replay the grant).
"""

import hashlib
import json
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from models.approval import ApprovalRecord

DB_ROW_TIMEOUT = 5.0  # seconds to wait for a sqlite3 connection

TERMINAL_STATUSES = ("completed", "failed", "rejected", "expired")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_hash(parameters: dict[str, Any]) -> str:
    """SHA-256 over a canonical JSON dump — used to verify that what gets
    executed is byte-for-byte what a human approved (no TOCTOU swap)."""
    return hashlib.sha256(
        json.dumps(parameters, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class ApprovalStore:
    """SQLite-backed approval ledger + audit log."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._connection = sqlite3.connect(
            db_path, check_same_thread=False, timeout=DB_ROW_TIMEOUT,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    @contextmanager
    def _cursor(self):
        with self._lock:
            cursor = self._connection.cursor()
            try:
                yield cursor
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def _init_schema(self) -> None:
        with self._cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS approval_requests (
                    id                 TEXT PRIMARY KEY,
                    task_id            TEXT NOT NULL,
                    tenant_id          TEXT NOT NULL,
                    requested_by_key_id TEXT,
                    tool               TEXT NOT NULL,
                    parameters_json    TEXT NOT NULL,
                    params_hash        TEXT NOT NULL,
                    status             TEXT NOT NULL CHECK(status IN
                        ('pending_approval','approved','running','completed',
                         'failed','rejected','expired')),
                    execution_token_hash TEXT,
                    created_at         TEXT NOT NULL,
                    expires_at         TEXT NOT NULL,
                    approved_at        TEXT,
                    approved_by_key_id TEXT,
                    claimed_at         TEXT,
                    completed_at       TEXT,
                    error              TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_approvals_status
                ON approval_requests (status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_approvals_tenant
                ON approval_requests (tenant_id)
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    event TEXT NOT NULL,
                    approval_id TEXT NOT NULL,
                    task_id TEXT,
                    actor_key_id TEXT,
                    tenant_id TEXT,
                    detail TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_approval
                ON audit_log (approval_id)
            """)

    # ------------------------------------------------------------------
    # Ledger writes
    # ------------------------------------------------------------------

    def create(
        self, *, task_id: str, tenant_id: str, requested_by_key_id: str | None,
        tool: str, parameters: dict[str, Any], ttl_seconds: int,
    ) -> ApprovalRecord:
        approval_id = f"appr-{secrets.token_hex(4)}"
        now = _utc_now()
        expires = datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc)
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO approval_requests
                    (id, task_id, tenant_id, requested_by_key_id, tool,
                     parameters_json, params_hash, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?, ?)
                """,
                (
                    approval_id, task_id, tenant_id, requested_by_key_id, tool,
                    json.dumps(parameters, default=str),
                    canonical_hash(parameters),
                    now.isoformat(), expires.isoformat(),
                ),
            )
        record = self.get(approval_id)
        assert record is not None
        return record

    def set_token_hash(self, approval_id: str, token_hash: str) -> bool:
        """Store the SHA-256 of the one-time grant token (never the raw token)."""
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE approval_requests SET execution_token_hash = ? WHERE id = ?",
                (token_hash, approval_id),
            )
            return cursor.rowcount > 0

    def approve_and_claim(
        self, approval_id: str, *, tenant_id: str, actor_key_id: str | None,
    ) -> ApprovalRecord | None:
        """The single atomic approve+claim transition:
        pending_approval -> running, only while unexpired. Returns the
        claimed record, or None if the row wasn't in a claimable state
        (double approve, already running, terminal, or different tenant).
        This is the exactly-once enforcement point — callers must treat a
        None result as 'someone else already got there' (HTTP 409) and
        never dispatch."""
        now = _utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE approval_requests
                SET status = 'running', approved_at = ?, claimed_at = ?,
                    approved_by_key_id = ?
                WHERE id = ? AND tenant_id = ?
                  AND status = 'pending_approval' AND expires_at > ?
                """,
                (now.isoformat(), now.isoformat(), actor_key_id,
                 approval_id, tenant_id, now.isoformat()),
            )
            claimed = cursor.rowcount > 0
        return self.get(approval_id) if claimed else None

    def reject(self, approval_id: str, *, tenant_id: str) -> ApprovalRecord | None:
        """pending_approval -> rejected, atomically. A rejected action can
        never be approved or claimed afterwards (no grant is ever issued)."""
        now = _utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE approval_requests
                SET status = 'rejected', completed_at = ?
                WHERE id = ? AND tenant_id = ? AND status = 'pending_approval'
                """,
                (now.isoformat(), approval_id, tenant_id),
            )
            flipped = cursor.rowcount > 0
        return self.get(approval_id) if flipped else None

    def mark_expired(self, approval_id: str, *, reason: str = "expired before approval") -> ApprovalRecord | None:
        """pending_approval -> expired, atomically (only if still pending)."""
        now = _utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE approval_requests
                SET status = 'expired', completed_at = ?, error = ?
                WHERE id = ? AND status = 'pending_approval'
                """,
                (now.isoformat(), reason, approval_id),
            )
            flipped = cursor.rowcount > 0
        return self.get(approval_id) if flipped else None

    def finalize(
        self, approval_id: str, status: str, *, error: str | None = None,
        require_current: str = "running",
    ) -> ApprovalRecord | None:
        """Terminal transition from `require_current` (normally running ->
        completed/failed). Conditional so a stray second finalize can't
        overwrite a terminal state."""
        if status not in ("completed", "failed"):
            raise ValueError(f"finalize only accepts completed/failed, got {status!r}")
        now = _utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE approval_requests
                SET status = ?, completed_at = ?, error = ?
                WHERE id = ? AND status = ?
                """,
                (status, now.isoformat(), error, approval_id, require_current),
            )
            flipped = cursor.rowcount > 0
        return self.get(approval_id) if flipped else None

    def fail_from_pending(self, approval_id: str, *, error: str) -> ApprovalRecord | None:
        """Safe-failure path: pending_approval -> failed (used when dispatch
        setup itself breaks, so no row is stranded in a claimable state)."""
        now = _utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE approval_requests
                SET status = 'failed', completed_at = ?, error = ?
                WHERE id = ? AND status = 'pending_approval'
                """,
                (now.isoformat(), error, approval_id),
            )
            flipped = cursor.rowcount > 0
        return self.get(approval_id) if flipped else None

    # ------------------------------------------------------------------
    # Ledger reads
    # ------------------------------------------------------------------

    def get(self, approval_id: str) -> ApprovalRecord | None:
        """Raw row (parameters NOT sanitized) — for internal dispatch use.
        API responses must go through `to_public()`."""
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM approval_requests WHERE id = ?", (approval_id,))
            row = cursor.fetchone()
        return self._row_to_raw(row) if row else None

    def list(
        self, *, tenant_id: str, status: str | None = None, limit: int = 100,
    ) -> list[ApprovalRecord]:
        sql = "SELECT * FROM approval_requests WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [self._row_to_raw(row) for row in rows]

    def sweep_expired(self, *, tenant_id: str | None = None) -> list[ApprovalRecord]:
        """Move every still-pending row past its deadline to `expired`.
        Called lazily on list/approve — no background timer needed for a
        single-user local deployment."""
        now = _utc_now().isoformat()
        sql = "SELECT id FROM approval_requests WHERE status = 'pending_approval' AND expires_at <= ?"
        params: list[Any] = [now]
        if tenant_id:
            sql += " AND tenant_id = ?"
            params.append(tenant_id)
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            ids = [row["id"] for row in cursor.fetchall()]
        expired = []
        for approval_id in ids:
            record = self.mark_expired(approval_id)
            if record is not None:
                expired.append(record)
        return expired

    def params_snapshot(self, approval_id: str) -> tuple[dict[str, Any], str] | None:
        """Return (raw approved parameters, params_hash) for dispatch. The
        executor must use exactly these — never a re-submitted payload."""
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT parameters_json, params_hash FROM approval_requests WHERE id = ?",
                (approval_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["parameters_json"]), row["params_hash"]

    @staticmethod
    def is_expired(record: ApprovalRecord) -> bool:
        try:
            expires = datetime.fromisoformat(record.expires_at)
        except ValueError:
            return False
        return expires <= _utc_now()

    @staticmethod
    def to_public(record: ApprovalRecord) -> ApprovalRecord:
        """Copy with sanitized parameters for any API response."""
        return record.model_copy(update={"parameters": sanitize_parameters(record.parameters)})

    # ------------------------------------------------------------------
    # Audit log — APPEND-ONLY: there is deliberately no update/delete API
    # ------------------------------------------------------------------

    def audit(
        self, *, event: str, approval_id: str, task_id: str | None = None,
        actor_key_id: str | None = None, tenant_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_log (ts, event, approval_id, task_id, actor_key_id, tenant_id, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (_utc_now().isoformat(), event, approval_id, task_id,
                 actor_key_id, tenant_id, _truncate(detail) if detail else None),
            )

    def list_audit(
        self, *, tenant_id: str, approval_id: str | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM audit_log WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]
        if approval_id:
            sql += " AND approval_id = ?"
            params.append(approval_id)
        sql += " ORDER BY seq ASC LIMIT ?"  # ASC: audit trails read chronologically
        params.append(limit)
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def _row_to_raw(self, row: sqlite3.Row) -> ApprovalRecord:
        return ApprovalRecord(
            id=row["id"],
            task_id=row["task_id"],
            tenant_id=row["tenant_id"],
            tool=row["tool"],
            parameters=json.loads(row["parameters_json"]),
            status=row["status"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            approved_at=row["approved_at"],
            approved_by_key_id=row["approved_by_key_id"],
            claimed_at=row["claimed_at"],
            completed_at=row["completed_at"],
            error=row["error"],
        )


# ----------------------------------------------------------------------
# Sanitization
# ----------------------------------------------------------------------

SENSITIVE_KEY_RE = re.compile(r"secret|token|password|api[_-]?key", re.IGNORECASE)
MAX_VALUE_LENGTH = 200


def sanitize_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Redact anything that must never leave the backend in an API
    response or audit detail: secret-like keys by name, file content by
    key ('content'), and over-long values (kept as length + sha256 so a
    human can still verify what was approved matches what runs)."""
    sanitized: dict[str, Any] = {}
    for key, value in parameters.items():
        if SENSITIVE_KEY_RE.search(key):
            sanitized[key] = {"redacted": True}
        elif key == "content" and isinstance(value, str):
            sanitized[key] = {
                "redacted": True,
                "length": len(value),
                "sha256": hashlib.sha256(value.encode()).hexdigest()[:16],
            }
        elif isinstance(value, dict):
            sanitized[key] = sanitize_parameters(value)
        elif isinstance(value, str) and len(value) > MAX_VALUE_LENGTH:
            sanitized[key] = value[:MAX_VALUE_LENGTH] + f"… ({len(value)} chars total)"
        else:
            sanitized[key] = value
    return sanitized


def _truncate(text: str | None, limit: int = 500) -> str | None:
    if text is None:
        return None
    return text if len(text) <= limit else text[:limit] + "…"


# Singleton instance, same convention as memory/task_store.py. Default is
# in-memory (hermetic tests); deployments set AION_APPROVAL_DB_PATH.
default_approval_store: ApprovalStore | None = None


def get_default_approval_store() -> ApprovalStore:
    global default_approval_store
    if default_approval_store is None:
        from config import settings
        default_approval_store = ApprovalStore(settings.approval_db_path or ":memory:")
    return default_approval_store


def reset_approval_store() -> None:
    global default_approval_store
    default_approval_store = None
