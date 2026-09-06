"""Evidence resolution: for a claim, find lexical support or contradiction
within the context AION actually has — supplied memory strings and other
agents' outputs from the same task.

This is a word-overlap + negation-mismatch heuristic, not semantic
entailment. It is intentionally simple, deterministic, and testable. Its
limitation is stated here rather than hidden: two statements sharing enough
vocabulary and differing only in negation are treated as contradicting;
statements sharing vocabulary without a negation mismatch are treated as
supporting. This will miss subtler contradictions and can be fooled by
paraphrase — it is a first, honest baseline, not a claim of true
understanding.
"""

import re

from models.verification import ClaimRecord, EvidenceRef

_WORD_PATTERN = re.compile(r"[a-zA-Z]+")
_NEGATION_WORDS = {"not", "no", "never", "isn't", "doesn't", "cannot", "can't", "won't", "false", "n't"}
_OVERLAP_THRESHOLD = 0.3  # fraction of shared significant words required to treat two statements as "about the same thing"


def keywords(text: str) -> set[str]:
    return {word.lower() for word in _WORD_PATTERN.findall(text) if len(word) > 3}


def overlap_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def has_negation(text: str) -> bool:
    words = set(re.findall(r"[a-zA-Z']+", text.lower()))
    return bool(words & _NEGATION_WORDS)


def resolve_evidence(
    claim: ClaimRecord, *, memory: list[str], peer_statements: list[tuple[str, str]]
) -> tuple[list[EvidenceRef], list[EvidenceRef]]:
    claim_keywords = keywords(claim.text)
    claim_negated = has_negation(claim.text)
    supporting: list[EvidenceRef] = []
    contradicting: list[EvidenceRef] = []

    for memory_item in memory:
        if overlap_ratio(claim_keywords, keywords(memory_item)) < _OVERLAP_THRESHOLD:
            continue
        relation = "contradicts" if has_negation(memory_item) != claim_negated else "supports"
        ref = EvidenceRef(content=memory_item, source="memory", relation=relation)
        (contradicting if relation == "contradicts" else supporting).append(ref)

    for agent_id, statement in peer_statements:
        if overlap_ratio(claim_keywords, keywords(statement)) < _OVERLAP_THRESHOLD:
            continue
        relation = "contradicts" if has_negation(statement) != claim_negated else "supports"
        ref = EvidenceRef(content=statement, source=f"agent:{agent_id}", relation=relation)
        (contradicting if relation == "contradicts" else supporting).append(ref)

    return supporting, contradicting
