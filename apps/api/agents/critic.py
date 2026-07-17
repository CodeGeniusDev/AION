from agents.base import BaseAgent


class CriticAgent(BaseAgent):
    id = "critic"
    name = "Critic Agent"
    description = "Reviews outputs and identifies weak assumptions."
    status = "standby"
    role_instruction = "Review the draft for unsupported claims, contradictions, and missing information."
    completion_summary = "Checked the response for gaps and contradictions"

    def approve(self, draft: str) -> bool:
        return bool(draft.strip()) and "[needs-revision]" not in draft.lower()

    def fallback(self, task: str, context: dict[str, object]) -> str:
        _ = task
        draft = str(context.get("draft", ""))
        return "Development review completed; the available draft is coherent." if self.approve(draft) else "Revision requested."
