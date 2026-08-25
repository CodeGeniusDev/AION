"""Task completion → memory consolidation.

This is the write path, and it is deliberately narrow: one episodic record
per completed task (what happened), plus zero or more semantic records —
one per claim the Immune System actually marked "verified" (never
"contradicted", never "insufficient_evidence"). This is NOT "store every
generated sentence" — it is exactly the opposite, by construction: the only
way a semantic record gets written is through
immune.memory_policy.memory_candidates(), which filters to verified claims
only.
"""

from models.chat import ChatMode
from models.cognitive_memory import MemoryRecord
from models.verification import ImmuneReport

from immune.memory_policy import memory_candidates
from memory.store import MemoryStoreInterface


def consolidate_task_memory(
    *,
    task_id: str,
    mode: ChatMode,
    execution_order: list[str],
    decision_reason: str,
    status: str,
    required_domains: list[str],
    immune_report: ImmuneReport | None,
    store: MemoryStoreInterface,
    tenant_id: str | None = None,
) -> list[MemoryRecord]:
    written: list[MemoryRecord] = []

    episodic = MemoryRecord(
        type="episodic",
        content=(
            f"Task ({mode} mode) ran agents {execution_order or '[]'} — {decision_reason} "
            f"Final status: {status}."
        ),
        task_id=task_id,
        source_agent="aion",
        verification_state="unverified",  # a log of what happened, not a claim about the world
        tags=list(required_domains),
        provenance="workflow_runner",
        tenant_id=tenant_id,
    )
    written.append(store.write(episodic))

    if immune_report is not None:
        for verified_result in memory_candidates(immune_report):
            semantic = MemoryRecord(
                type="semantic",
                content=verified_result.claim.text,
                task_id=task_id,
                source_agent=verified_result.claim.source_agent,
                verification_state="verified",
                tags=list(required_domains),
                provenance=verified_result.verifier,
                tenant_id=tenant_id,
            )
            written.append(store.write(semantic))

    return written
