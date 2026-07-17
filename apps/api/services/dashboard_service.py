from models.dashboard import AgentActivity, DashboardResponse, RecentTask


def get_dashboard_data() -> DashboardResponse:
    """Return deterministic demo data until persistent storage is connected."""
    return DashboardResponse(
        total_tasks=128,
        active_agents=4,
        saved_memories=24,
        system_health=98,
        recent_tasks=[
            RecentTask(
                id="task-001",
                title="Summarize product research",
                agent="Research Agent",
                status="completed",
                confidence=94,
            ),
            RecentTask(
                id="task-002",
                title="Plan the next development sprint",
                agent="Planner Agent",
                status="running",
                confidence=89,
            ),
            RecentTask(
                id="task-003",
                title="Review system assumptions",
                agent="Critic Agent",
                status="completed",
                confidence=91,
            ),
        ],
        agent_activity=[
            AgentActivity(name="Planner Agent", status="online", workload=72),
            AgentActivity(name="Research Agent", status="online", workload=58),
            AgentActivity(name="Critic Agent", status="standby", workload=24),
            AgentActivity(name="Memory Agent", status="online", workload=41),
        ],
    )

