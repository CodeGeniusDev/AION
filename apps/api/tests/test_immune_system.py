"""Tests for the AI Immune System (immune/*.py, models/verification.py).

Covers the six seeded cases required by Phase E, plus claim extraction,
evidence resolution mechanics, memory protection, WorkflowRunner/bus
integration, and existing chat/API regression.
"""

import asyncio

from fastapi.testclient import TestClient

from immune.claims import extract_claims
from immune.evidence import resolve_evidence
from immune.memory_policy import memory_candidates
from immune.system import ImmuneSystem
from main import app
from models.chat import ChatRequest
from models.verification import ClaimRecord, ImmuneReport, VerificationResult
from orchestration.workflow_runner import WorkflowRunner

client = TestClient(app)


def _claim(text: str, task_id: str = "task-x", source_agent: str = "aion") -> ClaimRecord:
    return ClaimRecord(text=text, source_agent=source_agent, task_id=task_id)


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------


def test_extract_claims_splits_sentences() -> None:
    claims = extract_claims("The bridge was built in 1932. It spans two rivers.", source_agent="a", task_id="t")
    assert len(claims) == 2


def test_extract_claims_excludes_questions() -> None:
    claims = extract_claims("Is this the right approach? We should verify it carefully.", source_agent="a", task_id="t")
    assert all(not c.text.endswith("?") for c in claims)
    assert len(claims) == 1


def test_extract_claims_excludes_short_fragments() -> None:
    claims = extract_claims("Yes. Also true. This is a complete standalone claim about something.", source_agent="a", task_id="t")
    assert all(len(c.text.split()) >= 4 for c in claims)


def test_extract_claims_on_empty_text_returns_empty_list() -> None:
    assert extract_claims("", source_agent="a", task_id="t") == []
    assert extract_claims("   ", source_agent="a", task_id="t") == []


# ---------------------------------------------------------------------------
# Evidence resolution mechanics
# ---------------------------------------------------------------------------


def test_resolve_evidence_finds_supporting_memory() -> None:
    claim = _claim("The bridge construction finished in nineteen thirty two")
    supporting, contradicting = resolve_evidence(
        claim, memory=["Historical records confirm bridge construction finished in nineteen thirty two."],
        peer_statements=[],
    )
    assert len(supporting) == 1
    assert contradicting == []


def test_resolve_evidence_finds_contradicting_memory() -> None:
    claim = _claim("The bridge construction finished in nineteen thirty two")
    supporting, contradicting = resolve_evidence(
        claim, memory=["Historical records show bridge construction did not finish in nineteen thirty two."],
        peer_statements=[],
    )
    assert len(contradicting) == 1


def test_resolve_evidence_ignores_unrelated_text() -> None:
    claim = _claim("The bridge construction finished in nineteen thirty two")
    supporting, contradicting = resolve_evidence(claim, memory=["The weather today is sunny and warm."], peer_statements=[])
    assert supporting == []
    assert contradicting == []


def test_resolve_evidence_checks_peer_agent_statements() -> None:
    claim = _claim("The launch budget was approved for next quarter")
    supporting, contradicting = resolve_evidence(
        claim, memory=[],
        peer_statements=[("researcher", "Records show the launch budget was approved for next quarter.")],
    )
    assert len(supporting) == 1
    assert supporting[0].source == "agent:researcher"


# ---------------------------------------------------------------------------
# Seeded case 1: two agents agree + supporting evidence -> verified
# ---------------------------------------------------------------------------


def test_seeded_case_agreement_with_evidence_is_verified() -> None:
    immune = ImmuneSystem()
    claim = _claim("The launch budget was approved for next quarter")
    result = immune.verify_claim(
        claim, memory=["Finance confirms the launch budget was approved for next quarter."],
        peer_statements=[("researcher", "The launch budget was approved for next quarter according to records.")],
    )
    assert result.status == "verified"
    assert result.risk == "low"
    assert len(result.supporting_evidence) == 2


# ---------------------------------------------------------------------------
# Seeded case 2: two agents disagree -> contradiction detected
# ---------------------------------------------------------------------------


def test_seeded_case_agent_disagreement_is_contradicted() -> None:
    immune = ImmuneSystem()
    claim = _claim("The launch budget was approved for next quarter")
    result = immune.verify_claim(
        claim, memory=[],
        peer_statements=[("critic", "The launch budget was not approved for next quarter based on the records.")],
    )
    assert result.status == "contradicted"
    assert result.risk == "high"
    assert len(result.contradicting_evidence) == 1


# ---------------------------------------------------------------------------
# Seeded case 3: claim has no evidence -> insufficient_evidence
# ---------------------------------------------------------------------------


def test_seeded_case_no_evidence_is_insufficient() -> None:
    immune = ImmuneSystem()
    claim = _claim("The quarterly roadmap includes three major milestones")
    result = immune.verify_claim(claim, memory=[], peer_statements=[])
    assert result.status == "insufficient_evidence"
    assert result.verifier_failed is False


# ---------------------------------------------------------------------------
# Seeded case 4: memory contains conflicting information -> contradiction
# ---------------------------------------------------------------------------


def test_seeded_case_memory_conflict_is_contradicted() -> None:
    immune = ImmuneSystem()
    claim = _claim("The quarterly roadmap includes three major milestones")
    result = immune.verify_claim(
        claim, memory=["Team notes: the quarterly roadmap does not include three major milestones."],
        peer_statements=[],
    )
    assert result.status == "contradicted"


# ---------------------------------------------------------------------------
# Seeded case 5: verifier itself fails -> never marked verified
# ---------------------------------------------------------------------------


def test_seeded_case_verifier_failure_never_marks_verified(monkeypatch) -> None:
    immune = ImmuneSystem()

    def _broken_resolver(*args, **kwargs):
        raise RuntimeError("simulated verifier failure")

    monkeypatch.setattr("immune.system.resolve_evidence", _broken_resolver)

    claim = _claim("The quarterly roadmap includes three major milestones")
    result = immune.verify_claim(claim, memory=["supporting note about roadmap milestones plan"], peer_statements=[])

    assert result.status != "verified"
    assert result.verifier_failed is True
    assert result.status == "insufficient_evidence"


def test_immune_decision_on_verifier_failure_requires_revision(monkeypatch) -> None:
    immune = ImmuneSystem()
    monkeypatch.setattr("immune.system.resolve_evidence", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    report = immune.evaluate(
        task_id="t", draft="This is a checkable claim about something specific.",
        used_agent_outputs={}, memory=[],
    )
    assert report.decision == "require_revision"
    assert all(r.status != "verified" for r in report.verification_results)


# ---------------------------------------------------------------------------
# Seeded case 6: high-risk unsupported claim -> stricter decision
# ---------------------------------------------------------------------------


def test_seeded_case_high_risk_unsupported_claim_is_critical_risk() -> None:
    immune = ImmuneSystem()
    claim = _claim("This approach is guaranteed to work in every situation")
    result = immune.verify_claim(claim, memory=[], peer_statements=[])
    assert result.status == "insufficient_evidence"
    assert result.risk == "critical"


def test_high_risk_unsupported_claim_forces_require_revision_decision() -> None:
    immune = ImmuneSystem()
    report = immune.evaluate(
        task_id="t", draft="This approach is guaranteed to work in every situation.",
        used_agent_outputs={}, memory=[],
    )
    assert report.decision == "require_revision"


def test_ordinary_unsupported_claim_only_warns_not_requires_revision() -> None:
    """Contrast case: an unsupported claim WITHOUT high-risk language gets
    the lighter pass_with_warning decision, confirming the stricter path
    above is genuinely risk-driven, not triggered by any unsupported claim."""
    immune = ImmuneSystem()
    report = immune.evaluate(
        task_id="t", draft="The quarterly roadmap includes three major milestones.",
        used_agent_outputs={}, memory=[],
    )
    assert report.decision == "pass_with_warning"


# ---------------------------------------------------------------------------
# Decision logic: additional combinations
# ---------------------------------------------------------------------------


def test_decision_pass_when_all_claims_supported() -> None:
    immune = ImmuneSystem()
    report = immune.evaluate(
        task_id="t", draft="The launch budget was approved for next quarter.",
        used_agent_outputs={"researcher": "Finance records confirm the launch budget was approved for next quarter."},
        memory=["The launch budget was approved for next quarter per finance."],
    )
    assert report.decision == "pass"


def test_decision_reject_when_multiple_claims_contradicted() -> None:
    immune = ImmuneSystem()
    report = immune.evaluate(
        task_id="t",
        draft="The launch budget was approved for next quarter. The review meeting was scheduled for Friday.",
        used_agent_outputs={
            "researcher": "The launch budget was not approved for next quarter, records show.",
            "critic": "The review meeting was not scheduled for Friday, records show.",
        },
        memory=[],
    )
    assert report.decision == "reject"


def test_evaluate_with_no_extractable_claims_passes_trivially() -> None:
    immune = ImmuneSystem()
    report = immune.evaluate(task_id="t", draft="Yes. Ok.", used_agent_outputs={}, memory=[])
    assert report.claims_checked == 0
    assert report.decision == "pass"


# ---------------------------------------------------------------------------
# Memory protection / write policy
# ---------------------------------------------------------------------------


def test_memory_candidates_only_includes_verified_claims() -> None:
    verified = VerificationResult(claim=_claim("A"), status="verified", risk="low", reasoning_summary="ok")
    partial = VerificationResult(claim=_claim("B"), status="partially_verified", risk="medium", reasoning_summary="ok")
    insufficient = VerificationResult(claim=_claim("C"), status="insufficient_evidence", risk="medium", reasoning_summary="ok")
    contradicted = VerificationResult(claim=_claim("D"), status="contradicted", risk="high", reasoning_summary="ok")
    report = ImmuneReport(
        task_id="t", claims_checked=4,
        verification_results=[verified, partial, insufficient, contradicted],
        decision="pass_with_warning", decision_reason="mixed",
    )
    candidates = memory_candidates(report)
    assert len(candidates) == 1
    assert candidates[0].claim.text == "A"


def test_memory_candidates_empty_when_nothing_verified() -> None:
    partial = VerificationResult(claim=_claim("B"), status="partially_verified", risk="medium", reasoning_summary="ok")
    report = ImmuneReport(task_id="t", claims_checked=1, verification_results=[partial], decision="pass_with_warning", decision_reason="x")
    assert memory_candidates(report) == []


# ---------------------------------------------------------------------------
# WorkflowRunner / Cognitive Bus integration
# ---------------------------------------------------------------------------


def run_chat(request: ChatRequest, runner: WorkflowRunner | None = None):
    return asyncio.run((runner or WorkflowRunner()).run(request))


def test_workflow_runner_produces_a_retrievable_immune_report() -> None:
    runner = WorkflowRunner()
    response = run_chat(ChatRequest(message="Research and compare solar options"), runner)
    report = runner.get_immune_report(response.task_id)
    assert report is not None
    assert report.task_id == response.task_id


def test_immune_events_are_published_to_the_bus() -> None:
    runner = WorkflowRunner()
    response = run_chat(ChatRequest(message="Research and compare solar options"), runner)
    intents = [message.intent for message in runner.bus.get_task_messages(response.task_id)]
    assert "immune_claims_extracted" in intents
    assert "immune_decision" in intents


def test_immune_disabled_flag_produces_no_report() -> None:
    runner = WorkflowRunner(enable_immune=False)
    response = run_chat(ChatRequest(message="Research and compare solar options"), runner)
    assert runner.get_immune_report(response.task_id) is None
    intents = [message.intent for message in runner.bus.get_task_messages(response.task_id)]
    assert "immune_decision" not in intents


def test_immune_evaluation_internal_failure_does_not_crash_chat(monkeypatch) -> None:
    runner = WorkflowRunner()

    def _broken_evaluate(*args, **kwargs):
        raise RuntimeError("simulated immune system crash")

    monkeypatch.setattr(runner.immune_system, "evaluate", _broken_evaluate)

    response = run_chat(ChatRequest(message="Research and compare solar options"), runner)

    assert response.status == "completed"  # chat still succeeds
    report = runner.get_immune_report(response.task_id)
    assert report is not None
    assert report.decision == "require_revision"
    assert all(r.status != "verified" for r in report.verification_results)


# ---------------------------------------------------------------------------
# Existing chat/API regression
# ---------------------------------------------------------------------------


def test_chat_endpoint_response_shape_unchanged_after_immune_integration() -> None:
    response = client.post("/api/chat", json={"message": "Summarize the plan"})
    assert response.status_code == 200
    body = response.json()
    for field in ("task_id", "conversation_id", "answer", "mode", "status", "used_agents", "confidence"):
        assert field in body
    # Verification metadata is intentionally NOT part of the public contract yet.
    assert "verification" not in body
    assert "immune" not in body


def test_dashboard_and_agents_endpoints_still_work() -> None:
    assert client.get("/api/dashboard").status_code == 200
    assert client.get("/api/agents").status_code == 200
