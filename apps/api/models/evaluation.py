"""Evaluation & Benchmarking schemas.

Every metric here is either measured directly from a real run, or
explicitly None with a stated reason when it cannot be measured with the
current architecture. Nothing is estimated or invented to fill a gap.

Ground truth for benchmark cases (expected_agents, expect_contradiction,
expect_insufficient) is not "fabricated results" — it is the researcher's
own construction: these are cases we author specifically so we know, by
construction, what the correct answer is (e.g. we write two literally
contradicting sentences and label the case "expects contradiction"). This
is standard benchmark methodology, distinct from inventing a measured
outcome.
"""

from typing import Literal

from pydantic import BaseModel, Field

BenchmarkCategory = Literal[
    "planning", "research", "reasoning", "memory", "multi_agent", "contradiction", "unsupported_claim"
]
ConfigurationName = Literal["baseline_pipeline", "aion_no_immune", "aion_full"]


class BenchmarkCase(BaseModel):
    case_id: str
    category: BenchmarkCategory
    message: str
    mode: str = "auto"
    memory: list[str] = Field(default_factory=list)
    selected_agents: list[str] = Field(default_factory=list)  # only used when mode == "manual"
    # Ground truth for pipeline cases (planning/research/reasoning/memory/multi_agent):
    expected_agents: list[str] = Field(default_factory=list)
    # Ground truth for immune-layer-only cases (contradiction/unsupported_claim).
    # These do not run through the live chat pipeline — see runner.py for why.
    immune_draft: str | None = None
    immune_peer_statements: list[tuple[str, str]] = Field(default_factory=list)
    expect_contradiction: bool = False
    expect_insufficient: bool = False


class CaseResult(BaseModel):
    case_id: str
    category: str
    configuration: str
    success: bool
    selected_agents: list[str] = Field(default_factory=list)
    confidence: float | None = None
    processing_time_ms: int | None = None
    revision_count: int = 0
    immune_decision: str | None = None
    detected_contradiction: bool | None = None
    detected_insufficient: bool | None = None
    error: str | None = None


class EvaluationSummary(BaseModel):
    configuration: str
    cases_run: int
    task_success_rate: float
    failure_rate: float
    mean_latency_ms: float | None
    median_latency_ms: float | None
    mean_confidence_on_success: float | None
    mean_confidence_on_failure: float | None
    agent_selection_precision: float | None
    agent_selection_recall: float | None
    revision_rate: float | None
    revision_success_rate: float | None
    contradiction_detection_rate: float | None
    unsupported_claim_detection_rate: float | None
    false_positive_rate: float | None
    false_negative_rate: float | None
    memory_retrieval_relevance: float | None = None
    memory_pollution_rate: float | None = None
    notes: list[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    configuration: str
    case_results: list[CaseResult]
    summary: EvaluationSummary
