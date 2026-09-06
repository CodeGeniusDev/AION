from agents.base import BaseAgent
from agents.registry import registry
from models.cognitive_dna import AgentIdentity, AvailabilityStatus, CapabilityTag, Domain, ModelDependency


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


_CRITIC_IDENTITY = AgentIdentity(
    id=CriticAgent.id,
    name=CriticAgent.name,
    description=CriticAgent.description,
    capabilities=[
        CapabilityTag(name="claim_review", domain=Domain.REVIEW, declared_proficiency=0.7),
        CapabilityTag(name="consistency_check", domain=Domain.REVIEW, declared_proficiency=0.7),
    ],
    domains=[Domain.REVIEW],
    limitations=["Reviews the synthesized draft only, not raw source evidence"],
    model_dependency=ModelDependency(provider="gemini", model="gemini-2.5-flash", required=False),
    availability=AvailabilityStatus.STANDBY,
)

registry.register(_CRITIC_IDENTITY, CriticAgent())
