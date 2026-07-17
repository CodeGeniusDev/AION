from agents.base import BaseAgent


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
