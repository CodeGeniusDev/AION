"""Authentication/authorization schemas.

`ApiKeyRecord` stores only a hash of the key, never the raw secret.
`AuthenticatedPrincipal` is the resolved identity attached to a request
after successful authentication — it carries tenant_id and role, the two
things authorization decisions in this codebase are based on.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Role = Literal["admin", "user", "readonly"]


class ApiKeyRecord(BaseModel):
    key_id: str = Field(default_factory=lambda: f"key-{uuid4().hex[:10]}")
    tenant_id: str
    role: Role = "user"
    hashed_key: str  # SHA-256 of the raw key — see auth/hashing.py for why this is appropriate here
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active: bool = True


class AuthenticatedPrincipal(BaseModel):
    """The resolved identity for one authenticated request."""

    key_id: str
    tenant_id: str
    role: Role
