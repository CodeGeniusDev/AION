"""Claim extraction: identify checkable statements from agent output.

Deliberately simple and deterministic — not every sentence is a claim, and
this does not attempt deep NLP understanding. Questions and very short
fragments are excluded.
"""

import re

from models.verification import ClaimRecord

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MIN_CLAIM_WORDS = 4


def extract_claims(text: str, *, source_agent: str, task_id: str) -> list[ClaimRecord]:
    if not text or not text.strip():
        return []
    sentences = [sentence.strip() for sentence in _SENTENCE_SPLIT.split(text) if sentence.strip()]
    claims: list[ClaimRecord] = []
    for sentence in sentences:
        if sentence.endswith("?"):
            continue  # questions are not claims
        if len(sentence.split()) < _MIN_CLAIM_WORDS:
            continue  # too short to be a meaningful, checkable statement
        claims.append(ClaimRecord(text=sentence, source_agent=source_agent, task_id=task_id))
    return claims
