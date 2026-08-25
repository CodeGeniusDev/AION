"""Memory write policy: which verification outcomes are eligible for future
persistence.

This module does not write anything — AION has no persistent Cognitive
Memory yet (that is a separate, not-yet-built phase), so there is nothing to
write to. It exists so a future memory subsystem has a ready-made, honest
boundary: only 'verified' claims are ever eligible here, and everything
else is explicitly excluded rather than silently promoted. Being unable to
disprove something is not the same as it being trustworthy enough to
remember as fact.
"""

from models.verification import ImmuneReport, VerificationResult


def memory_candidates(report: ImmuneReport) -> list[VerificationResult]:
    return [result for result in report.verification_results if result.status == "verified"]
