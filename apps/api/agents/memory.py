from agents.base import BaseAgent


class MemoryAgent(BaseAgent):
    id = "memory"
    name = "Memory Agent"
    description = "Organizes context for later retrieval."
    status = "online"
    role_instruction = "Retrieve only relevant saved context and summarize it without inventing memories."
    completion_summary = "Checked available memory for relevant context"

    def fallback(self, task: str, context: dict[str, object]) -> str:
        _ = task
        memories = context.get("memories", [])
        return f"Retrieved {len(memories) if isinstance(memories, list) else 0} related memories in development mode."
