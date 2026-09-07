import re
from typing import Any

from agents.base import BaseAgent
from agents.registry import registry
from models.cognitive_dna import AgentIdentity, AvailabilityStatus, CapabilityTag, Domain, ModelDependency
from services.gemini import GeminiService


class CriticAgent(BaseAgent):
    """Reviews synthesized drafts for structural and content quality.

    Performs multi-layer review:
    1. Structural checks: minimum length, paragraph structure, hedging language
    2. Content checks: unsupported claims, placeholder text, contradictions
    3. LLM-assisted review: when model service is available, asks Gemini to
       identify weak assumptions, unsupported claims, and missing information.
    """

    id = "critic"
    name = "Critic Agent"
    description = "Reviews outputs and identifies weak assumptions."
    status = "standby"
    role_instruction = (
        "Review the draft for unsupported claims, contradictions, and missing information. "
        "Identify specific problems. Reply with APPROVED if the draft is acceptable, "
        "or list specific issues that need revision."
    )
    completion_summary = "Checked the response for gaps and contradictions"

    # --- Structural quality thresholds ---
    _MIN_DRAFT_LENGTH = 20
    _MAX_HEDGING_RATIO = 0.3  # max 30% hedging phrases per sentence

    _HEDGING_PHRASES = re.compile(
        r"\b(i think|maybe|probably|i guess|not sure|might be|could be|"
        r"i believe|it seems|possibly|perhaps|i assume)\b",
        re.IGNORECASE,
    )
    _PLACEHOLDER_PATTERNS = re.compile(
        r"\[needs-revision\]|TODO|FIXME|XXX|PLACEHOLDER|"
        r"<insert|fill in|replace with|lorem ipsum",
        re.IGNORECASE,
    )
    # Claims with specific numbers/dates that should have supporting context
    _UNSUPPORTED_CLAIM_PATTERNS = [
        re.compile(r"\b\d{1,3}(,\d{3})*\s+(million|billion|trillion)\b", re.IGNORECASE),
        re.compile(r"\b(19|20)\d{2}\b"),  # year references
    ]

    def _check_structural(self, draft: str) -> list[str]:
        """Return list of structural issues found."""
        issues: list[str] = []

        if len(draft.strip()) < self._MIN_DRAFT_LENGTH:
            issues.append(f"Draft too short ({len(draft.strip())} chars); likely incomplete")

        if self._PLACEHOLDER_PATTERNS.search(draft):
            issues.append("Draft contains placeholder text or revision markers")

        sentences = [s.strip() for s in re.split(r"[.!?]+", draft) if s.strip()]
        if not sentences:
            issues.append("Draft contains no complete sentences")

        # Check hedging language ratio
        hedging_count = sum(1 for s in sentences if self._HEDGING_PHRASES.search(s))
        if sentences and hedging_count / len(sentences) > self._MAX_HEDGING_RATIO:
            issues.append(f"Excessive hedging language ({hedging_count}/{len(sentences)} sentences)")

        return issues

    def _check_content(self, draft: str) -> list[str]:
        """Return list of content issues found."""
        issues: list[str] = []

        # Check for unsupported specific claims
        for pattern in self._UNSUPPORTED_CLAIM_PATTERNS:
            matches = pattern.findall(draft)
            if matches and len(draft) < 200:
                issues.append("Short draft contains specific claims that may lack supporting evidence")
                break

        # Check for repetitive content (same phrase repeated)
        words = draft.lower().split()
        if len(words) > 10:
            bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
            from collections import Counter
            bigram_counts = Counter(bigrams)
            repeated = {bg: count for bg, count in bigram_counts.items() if count > 2 and len(bg) > 5}
            if repeated:
                issues.append(f"Repetitive phrases detected: {list(repeated.keys())[:2]}")

        return issues

    def approve(self, draft: str) -> bool:
        """Synchronous structural review. Returns True if no issues found."""
        if not draft.strip():
            return False
        structural_issues = self._check_structural(draft)
        content_issues = self._check_content(draft)
        return len(structural_issues) == 0 and len(content_issues) == 0

    async def review_with_llm(self, draft: str, message: str, model_service: GeminiService) -> tuple[bool, list[str]]:
        """LLM-assisted review. Returns (approved, issues_list)."""
        # First do structural checks
        structural_issues = self._check_structural(draft)
        content_issues = self._check_content(draft)
        local_issues = structural_issues + content_issues

        if local_issues:
            return False, local_issues

        # If LLM is available, ask for deeper review
        if not model_service.is_configured():
            return True, []  # Structural checks passed, no LLM available

        prompt = (
            f"User request: {message}\n\n"
            f"Draft response:\n{draft}\n\n"
            f"Review this draft for:\n"
            f"1. Unsupported claims (specific numbers/dates without evidence)\n"
            f"2. Contradictions or logical gaps\n"
            f"3. Missing information the user would expect\n\n"
            f"If acceptable, respond with exactly: APPROVED\n"
            f"Otherwise, list specific issues (one per line, no numbering)."
        )

        review = await model_service.generate(self.role_instruction, prompt)
        if review is None:
            # LLM failed — fall back to structural checks (already passed)
            return True, []

        review = review.strip()
        if review.upper().startswith("APPROVED"):
            return True, []

        issues = [line.strip() for line in review.split("\n") if line.strip()]
        return False, issues[:5]  # cap at 5 issues

    def fallback(self, task: str, context: dict[str, object]) -> str:
        _ = task
        draft = str(context.get("draft", ""))
        if self.approve(draft):
            return "Development review completed; the available draft is coherent."
        issues = self._check_structural(draft) + self._check_content(draft)
        return f"Revision requested: {'; '.join(issues[:3])}"

    async def run(self, task: str, context: dict[str, Any], model_service: GeminiService) -> str:
        """Override base run to use LLM-assisted review."""
        draft = str(context.get("draft", ""))
        approved, issues = await self.review_with_llm(draft, task, model_service)
        if approved:
            return "Review passed — draft is acceptable."
        return f"[needs-revision] Issues found:\n" + "\n".join(f"- {issue}" for issue in issues)


_CRITIC_IDENTITY = AgentIdentity(
    id=CriticAgent.id,
    name=CriticAgent.name,
    description=CriticAgent.description,
    capabilities=[
        CapabilityTag(name="claim_review", domain=Domain.REVIEW, declared_proficiency=0.7),
        CapabilityTag(name="consistency_check", domain=Domain.REVIEW, declared_proficiency=0.7),
        CapabilityTag(name="structural_analysis", domain=Domain.REVIEW, declared_proficiency=0.8),
    ],
    domains=[Domain.REVIEW],
    limitations=["Reviews the synthesized draft only, not raw source evidence"],
    model_dependency=ModelDependency(provider="gemini", model="gemini-2.5-flash", required=False),
    availability=AvailabilityStatus.STANDBY,
)

registry.register(_CRITIC_IDENTITY, CriticAgent())
