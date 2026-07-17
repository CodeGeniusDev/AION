from dataclasses import dataclass

from models.chat import AgentId, ChatMode


@dataclass(frozen=True)
class RoutingDecision:
    selected_agents: list[AgentId]
    reason: str
    execution_order: list[AgentId]


class AgentRouter:
    """Deterministic, multilingual-friendly routing with extendable phrase groups."""

    intent_phrases = {
        "plan": {"plan", "roadmap", "steps", "strategy", "schedule", "mansuba", "bana do", "tarteeb"},
        "research": {"research", "compare", "analyze", "analyse", "investigate", "find information", "tehqeeq", "muqabla", "maloomat"},
        "critic": {"check", "review", "verify", "correct", "is this right", "jaiza", "tasdeeq", "sahi hai"},
        "memory": {"remember", "previous", "earlier", "saved", "last time", "yaad", "pehle", "pichla"},
        "complex": {"detailed", "comprehensive", "deep", "in-depth", "future", "mukammal", "tafseeli"},
    }

    def route(
        self,
        message: str,
        mode: ChatMode,
        selected_agents: list[AgentId],
        available_memory: list[str],
        memory_enabled: bool,
    ) -> RoutingDecision:
        if mode == "quick":
            return RoutingDecision([], "Quick Answer uses a direct AION response.", [])
        if mode == "manual":
            return RoutingDecision(selected_agents, "Agents were selected manually.", selected_agents)
        if mode == "research":
            agents: list[AgentId] = ["planner", "researcher", "critic"]
            if memory_enabled and available_memory:
                agents.append("memory")
            return RoutingDecision(agents, "Research Team uses planning, research, and verification.", agents)

        normalized = " ".join(message.casefold().split())
        intents = {name for name, phrases in self.intent_phrases.items() if any(phrase in normalized for phrase in phrases)}
        agents = []
        if "research" in intents:
            agents.extend(["planner", "researcher", "critic"])
        elif "plan" in intents:
            agents.append("planner")
        elif "critic" in intents:
            agents.append("critic")
        if "memory" in intents and memory_enabled:
            agents.insert(0, "memory")
        if "complex" in intents and "research" in intents and memory_enabled and available_memory:
            agents.append("memory")
        agents = list(dict.fromkeys(agents))
        if not agents:
            return RoutingDecision([], "The request is simple enough for a direct AION response.", [])
        names = ", ".join(agent.title() for agent in agents)
        return RoutingDecision(agents, f"AION selected {names} for the detected request intent.", agents)
