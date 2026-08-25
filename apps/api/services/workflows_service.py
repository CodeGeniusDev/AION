from models.workflows import Workflow, WorkflowsResponse

_WORKFLOWS: list[Workflow] = [
    Workflow(
        id="deep-research",
        name="Deep Research",
        description="Investigate a question, challenge the findings, and save the useful context.",
        agents=["Planner", "Research", "Critic", "Memory"],
        runs=42,
        state="Running",
    ),
    Workflow(
        id="decision-brief",
        name="Decision Brief",
        description="Turn complex inputs into a focused recommendation with reviewed evidence.",
        agents=["Research", "Critic", "Planner"],
        runs=18,
        state="Ready",
    ),
    Workflow(
        id="knowledge-capture",
        name="Knowledge Capture",
        description="Structure new information and route it into the appropriate memory layer.",
        agents=["Memory", "Critic"],
        runs=76,
        state="Ready",
    ),
]


def get_workflows() -> WorkflowsResponse:
    """Return deterministic demo workflow data until the workflow runner is persisted."""
    return WorkflowsResponse(items=_WORKFLOWS, total=len(_WORKFLOWS))
