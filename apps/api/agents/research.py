from agents.base import BaseAgent


class ResearchAgent(BaseAgent):
    id = "researcher"
    name = "Research Agent"
    description = "Collects and organizes information for the system."
    status = "online"
    role_instruction = "Collect relevant information and produce a concise evidence-aware draft."
    completion_summary = "Collected and organized relevant information"

    def fallback(self, task: str, context: dict[str, object]) -> str:
        _ = context
        return f"Research draft prepared in development mode for '{task}'. Connect Gemini and sources for live research."
