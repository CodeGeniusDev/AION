"""Benchmark runner: executes the dataset against one of three
configurations and computes real, measured metrics.

Configurations
--------------
  baseline_pipeline — legacy keyword AgentRouter, no Immune layer. This is
    "AION before Phases C/E": what the original fixed pipeline could do.
  aion_no_immune    — Dynamic Brain Formation (Phase C), no Immune layer.
    Isolates the effect of capability-based selection alone.
  aion_full         — Dynamic Brain Formation + Immune System (Phases C+E).

Pipeline cases (planning/research/reasoning/memory/multi_agent) run through
the real WorkflowRunner end-to-end. contradiction/unsupported_claim cases
run against ImmuneSystem directly — see dataset.py's module docstring for
why, and note this only produces a meaningful result under aion_full (the
other two configurations have no immune layer, by definition, so those
cases report success=True with no immune fields rather than a fabricated
comparison).
"""

import asyncio
import statistics

from immune.system import ImmuneSystem
from models.chat import ChatRequest
from models.evaluation import BenchmarkCase, CaseResult, ConfigurationName, EvaluationReport, EvaluationSummary
from orchestration.workflow_runner import WorkflowRunner

_CONFIG_FLAGS: dict[str, dict[str, bool]] = {
    "baseline_pipeline": {"use_dynamic_brain": False, "enable_immune": False},
    "aion_no_immune": {"use_dynamic_brain": True, "enable_immune": False},
    "aion_full": {"use_dynamic_brain": True, "enable_immune": True},
}
_IMMUNE_ONLY_CATEGORIES = {"contradiction", "unsupported_claim"}


class Evaluator:
    def run_case(self, case: BenchmarkCase, *, configuration: ConfigurationName) -> CaseResult:
        if case.category in _IMMUNE_ONLY_CATEGORIES:
            return self._run_immune_case(case, configuration=configuration)
        return self._run_pipeline_case(case, configuration=configuration)

    @staticmethod
    def _run_pipeline_case(case: BenchmarkCase, *, configuration: ConfigurationName) -> CaseResult:
        flags = _CONFIG_FLAGS[configuration]
        runner = WorkflowRunner(**flags)
        try:
            request = ChatRequest(
                message=case.message, mode=case.mode,
                selected_agents=case.selected_agents, memory_enabled=bool(case.memory),
            )
            response = asyncio.run(runner.run(request, available_memory=case.memory))
        except Exception as exc:  # a benchmark run must never crash the whole suite over one bad case
            return CaseResult(case_id=case.case_id, category=case.category, configuration=configuration, success=False, error=str(exc))

        report = runner.get_immune_report(response.task_id) if flags["enable_immune"] else None
        return CaseResult(
            case_id=case.case_id, category=case.category, configuration=configuration,
            success=response.status == "completed",
            selected_agents=[agent.id for agent in response.used_agents],
            confidence=response.confidence, processing_time_ms=response.processing_time_ms,
            revision_count=response.revision_count,
            immune_decision=report.decision if report else None,
        )

    @staticmethod
    def _run_immune_case(case: BenchmarkCase, *, configuration: ConfigurationName) -> CaseResult:
        if configuration != "aion_full":
            # No immune layer exists in this configuration, by definition —
            # not a failure, just not applicable. Reported as success with
            # no detection fields, never as a fabricated pass/fail.
            return CaseResult(case_id=case.case_id, category=case.category, configuration=configuration, success=True)

        immune = ImmuneSystem()
        report = immune.evaluate(
            task_id=case.case_id, draft=case.immune_draft or "",
            used_agent_outputs=dict(case.immune_peer_statements), memory=case.memory,
        )
        detected_contradiction = any(result.status == "contradicted" for result in report.verification_results)
        detected_insufficient = any(result.status == "insufficient_evidence" for result in report.verification_results)
        return CaseResult(
            case_id=case.case_id, category=case.category, configuration=configuration,
            success=True, immune_decision=report.decision,
            detected_contradiction=detected_contradiction, detected_insufficient=detected_insufficient,
        )

    def evaluate_dataset(self, dataset: list[BenchmarkCase], *, configuration: ConfigurationName) -> EvaluationReport:
        results = [self.run_case(case, configuration=configuration) for case in dataset]
        summary = self._summarize(dataset, results, configuration=configuration)
        return EvaluationReport(configuration=configuration, case_results=results, summary=summary)

    @staticmethod
    def _summarize(dataset: list[BenchmarkCase], results: list[CaseResult], *, configuration: str) -> EvaluationSummary:
        n = len(results)
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        task_success_rate = len(successes) / n if n else 0.0
        failure_rate = len(failures) / n if n else 0.0

        latencies = [r.processing_time_ms for r in results if r.processing_time_ms is not None]
        mean_latency = statistics.mean(latencies) if latencies else None
        median_latency = statistics.median(latencies) if latencies else None

        conf_success = [r.confidence for r in successes if r.confidence is not None]
        conf_failure = [r.confidence for r in failures if r.confidence is not None]
        mean_conf_success = statistics.mean(conf_success) if conf_success else None
        mean_conf_failure = statistics.mean(conf_failure) if conf_failure else None

        precisions: list[float] = []
        recalls: list[float] = []
        for case, result in zip(dataset, results):
            if case.category in _IMMUNE_ONLY_CATEGORIES:
                continue
            expected = set(case.expected_agents)
            predicted = set(result.selected_agents)
            if not expected and not predicted:
                precisions.append(1.0)
                recalls.append(1.0)
                continue
            if predicted:
                precisions.append(len(expected & predicted) / len(predicted))
            if expected:
                recalls.append(len(expected & predicted) / len(expected))
        precision = statistics.mean(precisions) if precisions else None
        recall = statistics.mean(recalls) if recalls else None

        revision_eligible = [r for r in results if r.category not in _IMMUNE_ONLY_CATEGORIES]
        revised = [r for r in revision_eligible if r.revision_count > 0]
        revision_rate = len(revised) / len(revision_eligible) if revision_eligible else None
        revision_success_rate = (sum(1 for r in revised if r.success) / len(revised)) if revised else None

        immune_pairs = [
            (case, result) for case, result in zip(dataset, results)
            if case.category in _IMMUNE_ONLY_CATEGORIES and configuration == "aion_full"
        ]
        contradiction_pairs = [(c, r) for c, r in immune_pairs if c.expect_contradiction]
        insufficient_pairs = [(c, r) for c, r in immune_pairs if c.expect_insufficient]
        clean_pairs = [(c, r) for c, r in immune_pairs if not c.expect_contradiction and not c.expect_insufficient]

        contradiction_detection_rate = (
            sum(1 for c, r in contradiction_pairs if r.detected_contradiction) / len(contradiction_pairs)
            if contradiction_pairs else None
        )
        unsupported_detection_rate = (
            sum(1 for c, r in insufficient_pairs if r.detected_insufficient) / len(insufficient_pairs)
            if insufficient_pairs else None
        )
        false_positives = sum(1 for c, r in clean_pairs if r.detected_contradiction or r.detected_insufficient)
        false_positive_rate = false_positives / len(clean_pairs) if clean_pairs else None

        false_negatives = (
            sum(1 for c, r in contradiction_pairs if not r.detected_contradiction)
            + sum(1 for c, r in insufficient_pairs if not r.detected_insufficient)
        )
        total_expected_positive = len(contradiction_pairs) + len(insufficient_pairs)
        false_negative_rate = false_negatives / total_expected_positive if total_expected_positive else None

        notes: list[str] = []
        if configuration != "aion_full":
            notes.append("Immune-layer detection metrics only apply to the aion_full configuration; this run has no immune layer, by definition of the configuration.")
        notes.append(
            "memory_retrieval_relevance and memory_pollution_rate are not measurable: this codebase has no "
            "persistent Cognitive Memory (no embedding store, no durable retrieval) — reported as None rather than fabricated."
        )
        notes.append(
            "contradiction/unsupported_claim cases exercise the Immune System component directly with "
            "constructed inputs, not the full live-model chat pipeline: deterministic dev-mode agent fallback "
            "text is generic and does not vary by case content, so it cannot produce case-specific agreement "
            "or disagreement without a live model call."
        )

        return EvaluationSummary(
            configuration=configuration, cases_run=n,
            task_success_rate=round(task_success_rate, 3), failure_rate=round(failure_rate, 3),
            mean_latency_ms=mean_latency, median_latency_ms=median_latency,
            mean_confidence_on_success=mean_conf_success, mean_confidence_on_failure=mean_conf_failure,
            agent_selection_precision=precision, agent_selection_recall=recall,
            revision_rate=revision_rate, revision_success_rate=revision_success_rate,
            contradiction_detection_rate=contradiction_detection_rate,
            unsupported_claim_detection_rate=unsupported_detection_rate,
            false_positive_rate=false_positive_rate, false_negative_rate=false_negative_rate,
            notes=notes,
        )

    @staticmethod
    def save_report(report: EvaluationReport, path: str) -> None:
        """Persist raw evaluation results as JSON for reproducibility."""
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(report.model_dump_json(indent=2))

    @staticmethod
    def load_report(path: str) -> EvaluationReport:
        with open(path, encoding="utf-8") as handle:
            return EvaluationReport.model_validate_json(handle.read())
