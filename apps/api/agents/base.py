from typing import Any, Literal

from services.gemini import GeminiService

AgentStatus = Literal["online", "standby", "offline"]


class BaseAgent:
    """Shared agent interface. Agents never call model providers directly."""

    id: str = "base"
    name: str = "Base Agent"
    description: str = "Base agent placeholder"
    status: AgentStatus = "standby"
    role_instruction: str = "Help AION complete the assigned task."
    completion_summary: str = "Completed assigned work"

    async def run(
        self,
        task: str,
        context: dict[str, Any],
        model_service: GeminiService,
    ) -> str:
        prompt = f"Task: {task}\nAvailable context: {context}"
        generated = await model_service.generate(self.role_instruction, prompt)
        return generated or self.fallback(task, context)

    def fallback(self, task: str, context: dict[str, Any]) -> str:
        _ = context
        return f"{self.name} completed its development-mode pass for: {task}"
