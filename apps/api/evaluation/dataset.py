"""Deterministic benchmark dataset.

Two kinds of ground truth here, both genuine (neither is a fabricated
result):

  1. `expected_agents` for pipeline cases — we know which Cognitive DNA
     domains a message is written to trigger, because we authored the
     message against DynamicBrainFormer's documented phrase vocabulary
     (orchestration/brain_former.py::DOMAIN_PHRASES). This is the correct
     agent selection by construction.

  2. `expect_contradiction` / `expect_insufficient` for immune cases — we
     construct the draft/peer-statement/memory text ourselves, specifically
     to contain (or not contain) a lexical contradiction or missing
     evidence. We know the correct verification outcome because we wrote
     the inputs to have it.

Neither is "invented results" — both are standard benchmark-authoring
practice: control the input, know the correct output, measure whether the
system under test finds it.

contradiction/unsupported_claim cases are evaluated against the Immune
System component directly (see evaluation/runner.py), not through the full
live chat pipeline — deterministic dev-mode agent fallback text is generic
boilerplate unrelated to any specific case's content, so it cannot be made
to agree or disagree about anything case-specific without a live model
call. This is a stated limitation, not hidden.
"""

from models.evaluation import BenchmarkCase


def build_default_dataset() -> list[BenchmarkCase]:
    return [
        BenchmarkCase(
            case_id="plan-01", category="planning",
            message="Create a roadmap and steps for launch",
            expected_agents=["planner"],
        ),
        BenchmarkCase(
            case_id="plan-02", category="planning",
            message="Build a strategy and schedule for the migration",
            expected_agents=["planner"],
        ),
        BenchmarkCase(
            case_id="research-01", category="research",
            message="Research and compare solar options",
            expected_agents=["planner", "researcher", "critic"],
        ),
        BenchmarkCase(
            case_id="research-02", category="research",
            message="Investigate and analyze these two vendors",
            expected_agents=["planner", "researcher", "critic"],
        ),
        BenchmarkCase(
            case_id="reasoning-01", category="reasoning",
            message="Explain photosynthesis simply",
            expected_agents=[],
        ),
        BenchmarkCase(
            case_id="reasoning-02", category="reasoning",
            message="What is the boiling point of water",
            expected_agents=[],
        ),
        BenchmarkCase(
            case_id="memory-01", category="memory",
            message="Remember what we discussed earlier and check it",
            memory=["We discussed the Q3 budget last time."],
            expected_agents=["critic", "memory"],
        ),
        BenchmarkCase(
            case_id="memory-02", category="memory",
            message="Use saved context and verify it", mode="manual",
            selected_agents=["memory", "critic"],
            expected_agents=["memory", "critic"],
        ),
        BenchmarkCase(
            case_id="multi-01", category="multi_agent",
            message="Research, plan, and verify our product launch",
            expected_agents=["planner", "researcher", "critic"],
        ),
        BenchmarkCase(
            case_id="multi-02", category="multi_agent",
            message="Hi there", mode="quick",
            expected_agents=[],
        ),
        BenchmarkCase(
            case_id="contradiction-01", category="contradiction",
            message="(immune-layer case, not a live chat message)",
            immune_draft="The launch budget was approved for next quarter.",
            immune_peer_statements=[("critic", "The launch budget was not approved for next quarter based on the records.")],
            expect_contradiction=True,
        ),
        BenchmarkCase(
            case_id="contradiction-02", category="contradiction",
            message="(immune-layer case, not a live chat message)",
            immune_draft="The quarterly roadmap includes three major milestones.",
            memory=["Team notes: the quarterly roadmap does not include three major milestones."],
            expect_contradiction=True,
        ),
        BenchmarkCase(
            case_id="contradiction-03-clean", category="contradiction",
            message="(immune-layer case, not a live chat message)",
            immune_draft="The launch budget was approved for next quarter.",
            immune_peer_statements=[("researcher", "Finance records confirm the launch budget was approved for next quarter.")],
            memory=["The launch budget was approved for next quarter per finance."],
            expect_contradiction=False, expect_insufficient=False,
        ),
        BenchmarkCase(
            case_id="unsupported-01", category="unsupported_claim",
            message="(immune-layer case, not a live chat message)",
            immune_draft="The quarterly roadmap includes three major milestones.",
            expect_insufficient=True,
        ),
        BenchmarkCase(
            case_id="unsupported-02-high-risk", category="unsupported_claim",
            message="(immune-layer case, not a live chat message)",
            immune_draft="This approach is guaranteed to work in every situation.",
            expect_insufficient=True,
        ),
    ]
