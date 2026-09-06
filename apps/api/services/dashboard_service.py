"""Dashboard API service.

Aggregates real counts from the live Agent Registry and Cognitive Memory
store — the same subsystems /api/agents, /api/memory, /api/tasks now read
from. No invented numbers: total_tasks/saved_memories/active_agents are
real counts measured at request time. `system_health` and `workload` have
no real underlying metric anywhere in this codebase (no health-check
subsystem exists) — they are presentational placeholders, explicitly
documented as such rather than silently presented as measured data.
"""

from agents.registry import registry as agent_registry
from memory.store import MemoryStoreInterface
from models.cognitive_dna import AvailabilityStatus
from models.dashboard import AgentActivity, DashboardResponse, RecentTask
from services.tasks_service import _parse_agent, _parse_status


def get_dashboard(store: MemoryStoreInterface) -> DashboardResponse:
    identities = agent_registry.list_identities()
    active_agents = sum(1 for identity in identities if identity.availability != AvailabilityStatus.OFFLINE)

    recent_records = store.list_recent(memory_type="episodic", limit=5)
    recent_tasks = []
    for record in recent_records:
        status = _parse_status(record.content)
        recent_tasks.append(RecentTask(
            id=record.memory_id, title=record.content[:70], agent=_parse_agent(record.content),
            status=status, confidence=100 if status == "completed" else 0,
        ))

    agent_activity = [
        AgentActivity(
            name=identity.name,
            status=identity.availability.value if identity.availability.value in ("online", "standby", "offline") else "online",
            # No real per-agent load metric exists (no queueing/concurrency
            # tracking) — presentational placeholder, not measured.
            workload=50,
        )
        for identity in identities
    ]

    return DashboardResponse(
        total_tasks=len(store.list_recent(memory_type="episodic", limit=10_000)),
        active_agents=active_agents,
        saved_memories=store.count(),
        system_health=100,  # no real health-check subsystem exists; presentational only
        recent_tasks=recent_tasks,
        agent_activity=agent_activity,
    )
