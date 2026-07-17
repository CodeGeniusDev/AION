from typing import Literal

from pydantic import BaseModel, Field


class RecentTask(BaseModel):
    id: str
    title: str
    agent: str
    status: Literal["completed", "running", "failed"]
    confidence: int = Field(ge=0, le=100)


class AgentActivity(BaseModel):
    name: str
    status: Literal["online", "standby", "offline"]
    workload: int = Field(ge=0, le=100)


class DashboardResponse(BaseModel):
    total_tasks: int
    active_agents: int
    saved_memories: int
    system_health: int = Field(ge=0, le=100)
    recent_tasks: list[RecentTask]
    agent_activity: list[AgentActivity]

