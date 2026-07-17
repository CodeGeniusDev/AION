from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class CognitiveMessage(BaseModel):
    task_id: str
    source_agent: str
    target_agent: str
    intent: str
    content: str
    context: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: Literal["pending", "processing", "completed", "failed"] = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

