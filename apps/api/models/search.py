"""Global search models (Phase 1E, GET /api/search).

Additive read-only surface. Every result is a pointer into an existing
store — search never invents data and never exposes approval or schedule
parameter values.
"""

from typing import Literal

from pydantic import BaseModel, Field

SearchResultType = Literal[
    "task",
    "approval",
    "agent",
    "workflow",
    "memory",
    "conversation",
    "alert",
    "schedule",
]


class SearchResult(BaseModel):
    type: SearchResultType
    id: str
    title: str
    subtitle: str = ""
    href: str
    snippet: str = ""
    score: int = Field(ge=0)


class SearchResponse(BaseModel):
    query: str
    total: int
    # Grouped by source: tasks, approvals, agents, workflows, memory,
    # conversations, alerts, schedules. Only non-empty groups are returned.
    groups: dict[str, list[SearchResult]]
