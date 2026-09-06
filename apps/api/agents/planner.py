from agents.base import BaseAgent
from agents.registry import registry
from models.cognitive_dna import AgentIdentity, CapabilityTag, Domain, ModelDependency


class PlannerAgent(BaseAgent):
    id = "planner"
    name = "Planner Agent"
    description = "Breaks goals into clear, coordinated steps."
    status = "online"
    role_instruction = "Create a concise execution plan with clear, ordered subtasks."
    completion_summary = "Created a concise task plan"

    def fallback(self, task: str, context: dict[str, object]) -> str:
        _ = context
        return f"Plan: clarify the outcome, gather required inputs, complete the work, and verify the result for '{task}'."


# Cognitive DNA: declarative identity only, no execution logic. See
# models/cognitive_dna.py for field semantics.
_PLANNER_IDENTITY = AgentIdentity(
    id=PlannerAgent.id,
    name=PlannerAgent.name,
    description=PlannerAgent.description,
    capabilities=[
        CapabilityTag(name="task_decomposition", domain=Domain.PLANNING, declared_proficiency=0.8),
        CapabilityTag(name="execution_ordering", domain=Domain.PLANNING, declared_proficiency=0.75),
    ],
    domains=[Domain.PLANNING],
    limitations=["No access to real-time scheduling or calendar data"],
    model_dependency=ModelDependency(provider="gemini", model="gemini-2.5-flash", required=False),
)

registry.register(_PLANNER_IDENTITY, PlannerAgent())
