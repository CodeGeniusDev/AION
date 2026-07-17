from time import perf_counter
from typing import Any
from uuid import uuid4

from agents import CriticAgent, MemoryAgent, PlannerAgent, ResearchAgent
from agents.base import BaseAgent
from cognitive_bus import CognitiveBus, CognitiveMessage
from models.chat import AgentId, ChatRequest, ChatResponse, UsedAgent
from orchestration.agent_router import AgentRouter
from orchestration.response_synthesizer import ResponseSynthesizer
from services.gemini import GeminiService


class WorkflowRunner:
    def __init__(self, agents: dict[AgentId, BaseAgent] | None = None) -> None:
        self.router = AgentRouter()
        self.model_service = GeminiService()
        self.synthesizer = ResponseSynthesizer()
        self.agents = agents or {
            "planner": PlannerAgent(),
            "researcher": ResearchAgent(),
            "critic": CriticAgent(),
            "memory": MemoryAgent(),
        }

    async def run(self, request: ChatRequest, available_memory: list[str] | None = None) -> ChatResponse:
        started = perf_counter()
        self.model_service.generated_live_response = False
        task_id = f"task-{uuid4().hex[:8]}"
        conversation_id = request.conversation_id or f"conversation-{uuid4().hex[:8]}"
        memories = available_memory or []
        decision = self.router.route(request.message, request.mode, request.selected_agents, memories, request.memory_enabled)
        bus = CognitiveBus()
        outputs: list[str] = []
        used_agents: list[UsedAgent] = []
        errors = 0
        critic_approved = False
        revision_count = 0

        for agent_id in decision.execution_order:
            agent = self.agents[agent_id]
            bus.publish(CognitiveMessage(task_id=task_id, source_agent="aion", target_agent=agent_id, intent="execute", content=request.message, status="processing"))
            try:
                context: dict[str, Any] = {"memories": memories, "draft": outputs[-1] if outputs else ""}
                output = await agent.run(request.message, context, self.model_service)
                outputs.append(output)
                summary = agent.completion_summary
                if agent_id == "memory":
                    summary = f"Retrieved {len(memories)} related memories"
                used_agents.append(UsedAgent(id=agent_id, name=agent.name, status="completed", summary=summary))
                bus.publish(CognitiveMessage(task_id=task_id, source_agent=agent_id, target_agent="aion", intent="result", content=summary, confidence=0.8, status="completed"))
            except Exception:
                errors += 1
                used_agents.append(UsedAgent(id=agent_id, name=agent.name, status="failed", summary="Could not complete the assigned step"))

        draft = await self.synthesizer.synthesize(request.message, outputs, self.model_service)
        if "critic" in decision.selected_agents and request.verification_enabled:
            critic = self.agents["critic"]
            critic_approved = isinstance(critic, CriticAgent) and critic.approve(draft)
            if not critic_approved:
                draft = await self.synthesizer.revise(request.message, draft, self.model_service)
                revision_count = 1
                critic_approved = isinstance(critic, CriticAgent) and critic.approve(draft)

        status = "failed" if decision.selected_agents and errors == len(decision.selected_agents) else "completed"
        development_mode = not self.model_service.generated_live_response
        confidence = self.calculate_confidence(
            total_agents=len(decision.selected_agents),
            completed_agents=len(decision.selected_agents) - errors,
            critic_approved=critic_approved,
            verification_enabled=request.verification_enabled,
            source_count=0,
            error_count=errors,
            development_mode=development_mode,
        )
        return ChatResponse(
            task_id=task_id,
            conversation_id=conversation_id,
            answer=draft if status == "completed" else "AION could not complete this task.",
            mode=request.mode,
            status=status,
            used_agents=used_agents,
            confidence=confidence,
            processing_time_ms=max(1, round((perf_counter() - started) * 1000)),
            selection_summary=decision.reason,
            sources=[],
            error="AION could not complete this task." if status == "failed" else None,
            development_mode=development_mode,
            revision_count=revision_count,
        )

    @staticmethod
    def calculate_confidence(
        *, total_agents: int, completed_agents: int, critic_approved: bool,
        verification_enabled: bool, source_count: int, error_count: int,
        development_mode: bool,
    ) -> float:
        completion_ratio = completed_agents / total_agents if total_agents else 1.0
        score = 0.50 + (0.25 * completion_ratio)
        score += 0.10 if critic_approved else 0.0
        score += 0.05 if verification_enabled else 0.0
        score += 0.05 if source_count > 0 else 0.0
        score -= min(error_count * 0.15, 0.45)
        score -= 0.08 if development_mode else 0.0
        return round(max(0.20, min(score, 0.99)), 2)
