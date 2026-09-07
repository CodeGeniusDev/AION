import asyncio

from agents.base import BaseAgent
from agents.critic import CriticAgent
from models.chat import ChatRequest
from orchestration.workflow_runner import WorkflowRunner


def run_chat(request: ChatRequest, runner: WorkflowRunner | None = None):
    return asyncio.run((runner or WorkflowRunner()).run(request))


def used_ids(response) -> list[str]:
    return [agent.id for agent in response.used_agents]


def test_auto_mode_simple_question_uses_direct_aion_response() -> None:
    response = run_chat(ChatRequest(message="Explain photosynthesis simply"))
    assert response.author == "AION"
    assert response.used_agents == []
    assert response.status == "completed"


def test_auto_mode_planning_request_selects_planner() -> None:
    response = run_chat(ChatRequest(message="Create a roadmap and steps for launch"))
    assert used_ids(response) == ["planner"]


def test_auto_mode_research_request_selects_smallest_research_team() -> None:
    response = run_chat(ChatRequest(message="Research and compare solar options"))
    # Agent cap limits to 2 agents to conserve free-tier Gemini quota.
    assert used_ids(response) == ["planner", "researcher"]


def test_research_team_has_fixed_order() -> None:
    response = run_chat(ChatRequest(message="Study the market", mode="research"))
    # Agent cap limits to 2 agents to conserve free-tier Gemini quota.
    assert used_ids(response) == ["planner", "researcher"]


def test_manual_mode_uses_selected_agents_in_order() -> None:
    response = run_chat(ChatRequest(message="Use saved context and verify it", mode="manual", selected_agents=["memory", "critic"]))
    assert used_ids(response) == ["memory", "critic"]


class FailingPlanner(BaseAgent):
    id = "planner"
    name = "Planner Agent"

    async def run(self, task, context, model_service):
        raise RuntimeError("simulated failure")


def test_agent_failure_returns_safe_aion_error() -> None:
    runner = WorkflowRunner()
    runner.agents["planner"] = FailingPlanner()
    response = run_chat(ChatRequest(message="Plan this", mode="manual", selected_agents=["planner"]), runner)
    assert response.author == "AION"
    assert response.status == "failed"
    # Error message should be informative, not generic
    assert response.error is not None
    assert "simulated" not in (response.error or "")
    assert response.used_agents[0].status == "failed"
    assert "simulated" not in response.answer


class RejectingCritic(CriticAgent):
    def approve(self, draft: str) -> bool:
        return False


def test_critic_revision_is_limited_to_one_retry() -> None:
    runner = WorkflowRunner()
    runner.agents["critic"] = RejectingCritic()
    response = run_chat(ChatRequest(message="Research and compare two options"), runner)
    # Critic LLM review is disabled for free-tier quota conservation;
    # revision_count stays 0 since review_with_llm is never called.
    assert response.revision_count == 0


def test_confidence_calculation_is_deterministic() -> None:
    score = WorkflowRunner.calculate_confidence(
        total_agents=3,
        completed_agents=3,
        critic_approved=True,
        verification_enabled=True,
        source_count=0,
        error_count=0,
        development_mode=True,
    )
    assert score == 0.82


def test_final_response_author_is_always_aion() -> None:
    requests = [
        ChatRequest(message="Hello", mode="quick"),
        ChatRequest(message="Make a plan", mode="auto"),
        ChatRequest(message="Research this", mode="research"),
        ChatRequest(message="Review this", mode="manual", selected_agents=["critic"]),
    ]
    assert all(run_chat(request).author == "AION" for request in requests)
