from agents.base import BaseAgent
from agents.registry import registry
from models.cognitive_dna import AgentIdentity, CapabilityTag, Domain, ModelDependency


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


_MEMORY_IDENTITY = AgentIdentity(
    id=MemoryAgent.id,
    name=MemoryAgent.name,
    description=MemoryAgent.description,
    capabilities=[
        CapabilityTag(name="context_retrieval", domain=Domain.MEMORY, declared_proficiency=0.6),
        CapabilityTag(name="relevance_filtering", domain=Domain.MEMORY, declared_proficiency=0.5),
    ],
    domains=[Domain.MEMORY],
    limitations=["No persistent store yet — memory is supplied by the caller per request"],
    model_dependency=ModelDependency(provider="gemini", model="gemini-2.5-flash", required=False),
)

registry.register(_MEMORY_IDENTITY, MemoryAgent())
