"""AI Immune System: the verification engine.

Independent from CriticAgent by design — see models/verification.py for the
exact distinction. Never marks a claim 'verified' on internal failure: an
exception during evidence resolution produces insufficient_evidence with
verifier_failed=True, not a false positive.
"""

from immune.claims import extract_claims
from immune.evidence import resolve_evidence
from models.verification import ClaimRecord, ImmuneDecision, ImmuneReport, RiskLevel, VerificationResult

_HIGH_RISK_KEYWORDS = {"guaranteed", "always works", "never fails", "100%", "risk-free", "completely safe"}


class ImmuneSystem:
    verifier_id = "aion-immune-v1"

    def verify_claim(
        self, claim: ClaimRecord, *, memory: list[str], peer_statements: list[tuple[str, str]]
    ) -> VerificationResult:
        try:
            supporting, contradicting = resolve_evidence(claim, memory=memory, peer_statements=peer_statements)
        except Exception as exc:  # must never propagate, and must never look like success
            return VerificationResult(
                claim=claim, status="insufficient_evidence", risk="high",
                verifier=self.verifier_id, verifier_failed=True,
                reasoning_summary=f"Verification could not complete due to an internal error: {exc}",
            )

        if contradicting:
            return VerificationResult(
                claim=claim, status="contradicted", supporting_evidence=supporting,
                contradicting_evidence=contradicting, risk="high", verifier=self.verifier_id,
                reasoning_summary=f"{len(contradicting)} conflicting statement(s) found in available context.",
            )

        if supporting:
            status = "verified" if len(supporting) >= 2 else "partially_verified"
            return VerificationResult(
                claim=claim, status=status, supporting_evidence=supporting,
                risk="low" if status == "verified" else "medium", verifier=self.verifier_id,
                reasoning_summary=f"{len(supporting)} supporting statement(s) found in available context.",
            )

        risk: RiskLevel = "critical" if self._is_high_risk(claim.text) else "medium"
        return VerificationResult(
            claim=claim, status="insufficient_evidence", risk=risk, verifier=self.verifier_id,
            reasoning_summary="No supporting or contradicting evidence found in available context.",
        )

    def evaluate(
        self, *, task_id: str, draft: str, used_agent_outputs: dict[str, str], memory: list[str]
    ) -> ImmuneReport:
        claims = extract_claims(draft, source_agent="aion", task_id=task_id)
        peer_statements = list(used_agent_outputs.items())
        results = [self.verify_claim(claim, memory=memory, peer_statements=peer_statements) for claim in claims]
        decision, reason = self._decide(results)
        return ImmuneReport(
            task_id=task_id, claims_checked=len(claims), verification_results=results,
            decision=decision, decision_reason=reason,
        )

    @staticmethod
    def _is_high_risk(text: str) -> bool:
        normalized = text.lower()
        return any(keyword in normalized for keyword in _HIGH_RISK_KEYWORDS)

    @staticmethod
    def _decide(results: list[VerificationResult]) -> tuple[ImmuneDecision, str]:
        if not results:
            return "pass", "No checkable claims were extracted; nothing to verify."

        contradicted = [r for r in results if r.status == "contradicted"]
        failed = [r for r in results if r.verifier_failed]
        insufficient = [r for r in results if r.status == "insufficient_evidence"]
        critical_insufficient = [r for r in insufficient if r.risk == "critical"]

        if len(contradicted) > 1:
            return "reject", f"{len(contradicted)} contradicted claims detected; output is not trustworthy as written."
        if contradicted:
            return "require_revision", "A claim conflicts with available context and should be revised."
        if failed:
            return "require_revision", "The verifier failed on one or more claims; flagged for review rather than approved."
        if critical_insufficient:
            return "require_revision", f"{len(critical_insufficient)} high-risk unsupported claim(s) require revision before this can be trusted."
        if insufficient and len(insufficient) == len(results):
            return "pass_with_warning", "No claims could be corroborated against available context."
        if insufficient:
            return "pass_with_warning", f"{len(insufficient)} of {len(results)} claim(s) lack supporting evidence."
        return "pass", "All checkable claims were supported by available context."
