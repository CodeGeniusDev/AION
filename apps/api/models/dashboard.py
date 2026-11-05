from typing import Literal
from pydantic import BaseModel, Field


class RecentTask(BaseModel):
    id: str
    title: str
    agent: str
    status: Literal["completed", "running", "failed", "pending", "pending_approval"]
    confidence: int = Field(default=0, ge=0, le=100)
    created: str | None = None
    updated: str | None = None
    duration_ms: float | None = None


class AgentActivity(BaseModel):
    id: str = ""
    name: str
    role: str = ""
    status: Literal[
        "idle", "planning", "researching", "reviewing", "executing",
        "waiting", "completed", "failed", "offline", "online", "standby"
    ] = "idle"
    current_task: str | None = None
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    workload: int = Field(default=0, ge=0, le=100)
    last_run_at: str | None = None
    average_latency_ms: float | None = None


class TaskCounts(BaseModel):
    total: int = 0
    completed: int = 0
    running: int = 0
    pending: int = 0
    failed: int = 0


class AgentStats(BaseModel):
    total_registered: int = 0
    executing: int = 0
    idle: int = 0
    standby: int = 0
    offline: int = 0


class MemoryStats(BaseModel):
    total_records: int = 0
    episodic_count: int = 0
    semantic_count: int = 0
    procedural_count: int = 0
    status: str = "operational"
    provider: str = "SQLiteMemoryStore"


class HealthComponentDetail(BaseModel):
    name: str
    status: Literal["healthy", "degraded", "unavailable", "not_configured", "unknown"]
    detail: str
    latency_ms: float | None = None


class SystemHealthDetail(BaseModel):
    score: int = Field(ge=0, le=100)
    status: Literal["healthy", "degraded", "unhealthy"]
    uptime_seconds: float = 0.0
    calculation: str = ""
    components: list[HealthComponentDetail] = Field(default_factory=list)


class DashboardResponse(BaseModel):
    # Core top-level fields for backward compatibility
    total_tasks: int
    active_agents: int
    saved_memories: int
    system_health: int = Field(ge=0, le=100)
    recent_tasks: list[RecentTask]
    agent_activity: list[AgentActivity]

    # Enhanced Phase 2 telemetry & stats
    task_counts: TaskCounts = Field(default_factory=TaskCounts)
    agent_stats: AgentStats = Field(default_factory=AgentStats)
    memory_stats: MemoryStats = Field(default_factory=MemoryStats)
    system_health_detail: SystemHealthDetail | None = None
