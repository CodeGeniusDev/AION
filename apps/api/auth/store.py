"""API key store: real, hashed-at-rest storage behind a replaceable
interface. `InMemoryApiKeyStore` is the current implementation —
process-lifetime, no persistence across restarts (matching this
codebase's existing default posture: SQLiteMemoryStore's default is also
`:memory:` — see memory/store.py). A future persistent store (e.g. backed
by the same SQLite file, or Postgres) implements `ApiKeyStoreInterface`;
no caller changes.
"""

from abc import ABC, abstractmethod

from auth.hashing import generate_api_key, hash_api_key, verify_api_key
from models.auth import ApiKeyRecord, Role


class ApiKeyStoreInterface(ABC):
    @abstractmethod
    def issue(self, *, tenant_id: str, role: Role = "user") -> tuple[str, ApiKeyRecord]:
        """Returns (raw_key, record). raw_key is shown exactly once here —
        it is never stored or retrievable again, only its hash is kept."""

    @abstractmethod
    def resolve(self, raw_key: str) -> ApiKeyRecord | None:
        """Return the record for a valid, active raw key, else None."""

    @abstractmethod
    def revoke(self, key_id: str) -> None: ...

    @abstractmethod
    def clear(self) -> None:
        """Remove all keys. Administrative/test use only."""


class InMemoryApiKeyStore(ApiKeyStoreInterface):
    def __init__(self) -> None:
        self._records: dict[str, ApiKeyRecord] = {}  # keyed by hashed_key

    def issue(self, *, tenant_id: str, role: Role = "user") -> tuple[str, ApiKeyRecord]:
        raw_key = generate_api_key()
        hashed = hash_api_key(raw_key)
        record = ApiKeyRecord(tenant_id=tenant_id, role=role, hashed_key=hashed)
        self._records[hashed] = record
        return raw_key, record

    def resolve(self, raw_key: str) -> ApiKeyRecord | None:
        hashed = hash_api_key(raw_key)
        record = self._records.get(hashed)
        if record is None or not record.active:
            return None
        if not verify_api_key(raw_key, record.hashed_key):
            return None
        return record

    def revoke(self, key_id: str) -> None:
        for hashed, record in list(self._records.items()):
            if record.key_id == key_id:
                del self._records[hashed]
                return

    def clear(self) -> None:
        self._records.clear()


# Process-wide default store, mirroring agents.registry.registry's pattern.
key_store = InMemoryApiKeyStore()
