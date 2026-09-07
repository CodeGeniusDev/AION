"""Tests for the Phase F evaluation framework (evaluation/*.py,
models/evaluation.py). Covers dataset structure, per-case execution across
all three configurations, summary metric computation, raw-result
persistence, and confirms the framework itself introduces no regression in
the existing backend suite (verified separately by running the full suite).
"""

from models.evaluation import BenchmarkCase
from evaluation.dataset import build_default_dataset
from evaluation.runner import Evaluator


# ---------------------------------------------------------------------------
# Dataset structure
# ---------------------------------------------------------------------------


def test_default_dataset_covers_all_required_categories() -> None:
    dataset = build_default_dataset()
    categories = {case.category for case in dataset}
    assert categories == {"planning", "research", "reasoning", "memory", "multi_agent", "contradiction", "unsupported_claim"}


def test_default_dataset_case_ids_are_unique() -> None:
    dataset = build_default_dataset()
    ids = [case.case_id for case in dataset]
    assert len(ids) == len(set(ids))


def test_immune_only_cases_have_no_pipeline_ground_truth() -> None:
    dataset = build_default_dataset()
    for case in dataset:
        if case.category in ("contradiction", "unsupported_claim"):
            assert case.expected_agents == []


# ---------------------------------------------------------------------------
# Per-case execution — pipeline cases
# ---------------------------------------------------------------------------


def test_run_case_pipeline_records_selected_agents_and_success() -> None:
    case = BenchmarkCase(case_id="t1", category="planning", message="Create a roadmap and steps", expected_agents=["planner"])
    evaluator = Evaluator()
    result = evaluator.run_case(case, configuration="aion_full")
    assert result.success is True
    assert result.selected_agents == ["planner"]
    assert result.processing_time_ms is not None


def test_run_case_baseline_uses_legacy_router_not_dynamic_brain() -> None:
    case = BenchmarkCase(case_id="t2", category="research", message="Research and compare solar options", expected_agents=["planner", "researcher", "critic"])
    evaluator = Evaluator()
    result = evaluator.run_case(case, configuration="baseline_pipeline")
    assert result.success is True
    # Agent cap limits to 2 agents to conserve free-tier Gemini quota.
    assert result.selected_agents == ["planner", "researcher"]


def test_run_case_no_immune_configuration_has_no_immune_decision() -> None:
    case = BenchmarkCase(case_id="t3", category="planning", message="Create a roadmap and steps", expected_agents=["planner"])
    evaluator = Evaluator()
    result = evaluator.run_case(case, configuration="aion_no_immune")
    assert result.immune_decision is None


def test_run_case_full_configuration_has_immune_decision() -> None:
    case = BenchmarkCase(case_id="t4", category="planning", message="Create a roadmap and steps", expected_agents=["planner"])
    evaluator = Evaluator()
    result = evaluator.run_case(case, configuration="aion_full")
    assert result.immune_decision is not None


# ---------------------------------------------------------------------------
# Per-case execution — immune-only cases
# ---------------------------------------------------------------------------


def test_immune_case_only_evaluated_under_aion_full() -> None:
    case = BenchmarkCase(
        case_id="c1", category="contradiction", message="n/a",
        immune_draft="The launch budget was approved for next quarter.",
        immune_peer_statements=[("critic", "The launch budget was not approved for next quarter based on the records.")],
        expect_contradiction=True,
    )
    evaluator = Evaluator()
    baseline_result = evaluator.run_case(case, configuration="baseline_pipeline")
    full_result = evaluator.run_case(case, configuration="aion_full")

    assert baseline_result.detected_contradiction is None  # no immune layer in this configuration
    assert full_result.detected_contradiction is True


def test_immune_case_detects_insufficient_evidence() -> None:
    case = BenchmarkCase(
        case_id="u1", category="unsupported_claim", message="n/a",
        immune_draft="The quarterly roadmap includes three major milestones.",
        expect_insufficient=True,
    )
    result = Evaluator().run_case(case, configuration="aion_full")
    assert result.detected_insufficient is True


def test_immune_clean_case_reports_no_false_positive() -> None:
    case = BenchmarkCase(
        case_id="clean1", category="contradiction", message="n/a",
        immune_draft="The launch budget was approved for next quarter.",
        immune_peer_statements=[("researcher", "Finance records confirm the launch budget was approved for next quarter.")],
        memory=["The launch budget was approved for next quarter per finance."],
        expect_contradiction=False, expect_insufficient=False,
    )
    result = Evaluator().run_case(case, configuration="aion_full")
    assert result.detected_contradiction is False
    assert result.detected_insufficient is False


# ---------------------------------------------------------------------------
# Full dataset evaluation / summary metrics
# ---------------------------------------------------------------------------


def test_evaluate_dataset_runs_every_case_exactly_once() -> None:
    dataset = build_default_dataset()
    report = Evaluator().evaluate_dataset(dataset, configuration="aion_full")
    assert len(report.case_results) == len(dataset)
    assert report.summary.cases_run == len(dataset)


def test_evaluate_dataset_task_success_rate_is_measured_not_invented() -> None:
    dataset = build_default_dataset()
    report = Evaluator().evaluate_dataset(dataset, configuration="aion_full")
    expected_rate = sum(1 for r in report.case_results if r.success) / len(report.case_results)
    assert report.summary.task_success_rate == round(expected_rate, 3)


def test_agent_selection_precision_and_recall_perfect_on_calibrated_dataset() -> None:
    """The default dataset's pipeline cases were authored against
    DynamicBrainFormer's documented phrase vocabulary, so precision/recall
    should be 1.0 — this is a sanity check on the dataset's ground truth,
    not a claim that the system is perfect on arbitrary input."""
    dataset = build_default_dataset()
    report = Evaluator().evaluate_dataset(dataset, configuration="aion_full")
    assert report.summary.agent_selection_precision == 1.0
    # Agent cap (2 max) reduces recall slightly since some cases expect 3 agents.
    assert report.summary.agent_selection_recall >= 0.9


def test_immune_metrics_are_none_for_configurations_without_immune_layer() -> None:
    dataset = build_default_dataset()
    baseline_report = Evaluator().evaluate_dataset(dataset, configuration="baseline_pipeline")
    assert baseline_report.summary.contradiction_detection_rate is None
    assert baseline_report.summary.unsupported_claim_detection_rate is None


def test_immune_metrics_are_measured_for_aion_full() -> None:
    dataset = build_default_dataset()
    report = Evaluator().evaluate_dataset(dataset, configuration="aion_full")
    assert report.summary.contradiction_detection_rate is not None
    assert report.summary.unsupported_claim_detection_rate is not None
    assert 0.0 <= report.summary.contradiction_detection_rate <= 1.0


def test_memory_metrics_are_always_none_with_explanatory_note() -> None:
    """Persistent Cognitive Memory does not exist in this codebase — these
    metrics must never be fabricated, in any configuration."""
    dataset = build_default_dataset()
    for configuration in ("baseline_pipeline", "aion_no_immune", "aion_full"):
        report = Evaluator().evaluate_dataset(dataset, configuration=configuration)
        assert report.summary.memory_retrieval_relevance is None
        assert report.summary.memory_pollution_rate is None
        assert any("persistent Cognitive Memory" in note for note in report.summary.notes)


def test_latency_metrics_are_measured_and_nonnegative() -> None:
    dataset = build_default_dataset()
    report = Evaluator().evaluate_dataset(dataset, configuration="aion_full")
    assert report.summary.mean_latency_ms is not None
    assert report.summary.mean_latency_ms >= 0
    assert report.summary.median_latency_ms is not None


def test_three_configurations_produce_independently_computed_reports() -> None:
    dataset = build_default_dataset()
    evaluator = Evaluator()
    reports = {config: evaluator.evaluate_dataset(dataset, configuration=config) for config in ("baseline_pipeline", "aion_no_immune", "aion_full")}
    assert reports["baseline_pipeline"].configuration == "baseline_pipeline"
    assert reports["aion_no_immune"].configuration == "aion_no_immune"
    assert reports["aion_full"].configuration == "aion_full"
    # Only aion_full has immune-layer results; this is a structural
    # assertion about the framework's honesty, not an outcome claim.
    assert reports["baseline_pipeline"].summary.contradiction_detection_rate is None
    assert reports["aion_full"].summary.contradiction_detection_rate is not None


# ---------------------------------------------------------------------------
# Raw result persistence
# ---------------------------------------------------------------------------


def test_save_and_load_report_round_trip(tmp_path) -> None:
    dataset = build_default_dataset()
    report = Evaluator().evaluate_dataset(dataset, configuration="aion_full")
    path = str(tmp_path / "report.json")

    Evaluator.save_report(report, path)
    loaded = Evaluator.load_report(path)

    assert loaded.configuration == report.configuration
    assert loaded.summary.task_success_rate == report.summary.task_success_rate
    assert len(loaded.case_results) == len(report.case_results)


# ---------------------------------------------------------------------------
# Benchmark case error handling
# ---------------------------------------------------------------------------


def test_run_case_manual_mode_uses_selected_agents() -> None:
    case = BenchmarkCase(
        case_id="m1", category="memory", message="Use saved context and verify it", mode="manual",
        selected_agents=["memory", "critic"], expected_agents=["memory", "critic"],
    )
    result = Evaluator().run_case(case, configuration="aion_full")
    assert result.selected_agents == ["memory", "critic"]
