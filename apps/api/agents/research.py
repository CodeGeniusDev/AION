from agents.base import BaseAgent
from agents.registry import registry
from models.cognitive_dna import AgentIdentity, CapabilityTag, Domain, ModelDependency, SafetyConstraint


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


_RESEARCH_IDENTITY = AgentIdentity(
    id=ResearchAgent.id,
    name=ResearchAgent.name,
    description=ResearchAgent.description,
    capabilities=[
        CapabilityTag(name="information_retrieval", domain=Domain.RESEARCH, declared_proficiency=0.7),
        CapabilityTag(name="evidence_synthesis", domain=Domain.RESEARCH, declared_proficiency=0.65),
    ],
    domains=[Domain.RESEARCH],
    limitations=["No live web access; limited to the backing model's training data"],
    model_dependency=ModelDependency(provider="gemini", model="gemini-2.5-flash", required=False),
    safety=SafetyConstraint(requires_verification=True),
)

registry.register(_RESEARCH_IDENTITY, ResearchAgent())
