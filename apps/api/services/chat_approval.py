"""Chat-driven approval requests: pending approvals from natural language.

This module is the ONLY way the chat pipeline can touch the approval
system, and it deliberately contains a tiny slice of it:

* It can CREATE a pending approval (`request_execution`). Nothing else.
* It never imports, calls or even references `approve_and_claim`,
  `reject` or `dispatch` — approval remains exclusively a human action
  through /api/approvals/{id}/approve (tests spy on those methods to
  prove the chat path never reaches them).
* It never sees a grant token: tokens are minted inside `dispatch`,
  which lives behind the human-only endpoint.
* Classification is capped at protected desktop tools. The safe
  model-exposed tools (calculator, text_analysis, current_datetime) are
  explicitly rejected as approval targets so a spoofed classifier
  output can never mint a "pending approval" for a tool the model can
  already run, and Gemini function declarations are untouched here.

Two detection layers, both fail-closed:
1. A deterministic heuristic (primary — zero cost, fully testable, and
   the only layer available when model calls are disabled).
2. An optional single Gemini `generate()` call that returns strict JSON
   (never `generate_with_tools`, never tool declarations). Its output is
   validated against the protected whitelist exactly like the heuristic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from observability.logging_config import get_logger
from models.chat import PendingApprovalInfo
from services.approval_service import (
    ApprovalError,
    get_approval_service,
    is_protected,
)

logger = get_logger("services.chat_approval")

# Sentence-level veto: questions, hypotheticals and auxiliary-phrased
# requests are conversation, never an action request.
_FILTER_PREFIX = re.compile(
    r"^(how|what|why|when|where|who|can|could|should|would|do|does|did"
    r"|is|are|am|maybe|perhaps|hypothetically|if\b|imagine|suppose)",
    re.IGNORECASE,
)

_QUOTED = re.compile(r"[\"“']([^\"”']+)[\"”']")
# ~/abs/windows paths or a bare filename with an extension.
_PATH = re.compile(
    r"(~/[A-Za-z0-9._/\-]+|/[A-Za-z0-9._/\-]+\.[A-Za-z0-9]{1,6}"
    r"|[A-Za-z0-9_\-./\\]*\.[A-Za-z0-9]{1,6})",
)
_URL = re.compile(r"https?://\S+")

_MAX_CONTENT = 4000
_MAX_PATH = 512


@dataclass
class DesktopIntent:
    tool: str
    parameters: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parameter validation (shared by heuristic and LLM layers)
# ---------------------------------------------------------------------------

_ALLOWED_PARAMETERS: dict[str, dict[str, int]] = {
    "file_write": {"path": _MAX_PATH, "content": _MAX_CONTENT},
    "file_read": {"path": _MAX_PATH},
    "file_copy": {"source": _MAX_PATH, "destination": _MAX_PATH},
    "desktop_open_app": {"name": 128},
    "desktop_screenshot": {},
    "browser_navigate": {"url": 1024},
    "browser_screenshot": {"url": 1024},
    # Phase 7: platform + text (+ optional media URL). Credentials, live
    # mode and everything else are NOT request parameters by construction.
    "social_post": {"platform": 32, "content": _MAX_CONTENT, "media_url": 1024},
}

# Any key matching this is dropped before it ever reaches the ledger —
# spoofed grant/approval-control fields in model or user output are inert.
_FORBIDDEN_KEY = re.compile(r"(token|grant|secret|hash|approval|approve)", re.IGNORECASE)


def validate_parameters(tool: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only the known parameters for a whitelisted tool, with length
    caps. Unknown tools/keys (a spoofed 'executor': 'bridge' for example)
    are dropped, never forwarded."""
    allowed = _ALLOWED_PARAMETERS.get(tool)
    if allowed is None:
        return {}
    clean: dict[str, Any] = {}
    for key, max_len in allowed.items():
        if _FORBIDDEN_KEY.search(key):
            continue
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            clean[key] = value.strip()[:max_len]
    return clean


# ---------------------------------------------------------------------------
# Layer 1: deterministic heuristic
# ---------------------------------------------------------------------------

# A clause only counts as an action request when it OPENS with an
# imperative verb (after optional "please"/"now"/"then" softeners).
# Questions, hypotheticals and mid-sentence mentions stay inert text —
# documented, predictable behaviour, and false positives are harmless
# anyway (a pending row a human must still decide, and it expires).
_CLAUSE_START = re.compile(
    r"^(?:please\s+|now\s+|then\s+|and\s+|also\s+|you\s+can\s+)*"
    r"(write|create|make|save|put|dump|copy|duplicate|read|open|view|load|"
    r"navigate|go|launch|post|share|publish)\b",
    re.IGNORECASE,
)


def _candidate_clauses(message: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", message)
    return [
        p.strip() for p in parts
        if p.strip() and _CLAUSE_START.match(p.strip()) and not _FILTER_PREFIX.match(p.strip())
    ]


def _find_path(clause: str) -> str | None:
    match = _PATH.search(clause)
    return match.group(1) if match else None


def _quoted(clause: str) -> str | None:
    match = _QUOTED.search(clause)
    return match.group(1) if match else None


def detect_desktop_intent(message: str) -> DesktopIntent | None:
    """Deterministic intent detection for protected desktop actions.

    Only IMPERATIVE requests with a concrete target match ("Write ... to
    ~/notes.txt"); questions and hypotheticals about file operations never
    do. False positives are harmless: the worst case is a pending approval
    no human will approve (it expires on its own)."""
    for clause in _candidate_clauses(message):
        intent = _detect_clause(clause)
        if intent is not None and is_protected(intent.tool):
            return intent
    return None


def _detect_clause(clause: str) -> DesktopIntent | None:
    lowered = clause.lower()

    # social_post: "post/share/publish \"text\" to <official platform>" —
    # only the four scaffolded platforms match, and the quoted content is
    # required so stray prose about "posting" stays inert. The bridge
    # executor then runs dry-run unless its own config enables live.
    if re.match(r"^(?:please\s+)?(?:post|share|publish)\b", lowered):
        pm = re.search(
            r"\b(?:to|on)\s+(?:my\s+)?(facebook|instagram|pinterest|tiktok)\b",
            lowered,
        )
        content = _quoted(clause)
        if pm and content:
            raw: dict[str, Any] = {"platform": pm.group(1), "content": content}
            url = _URL.search(clause)
            if url:
                raw["media_url"] = url.group(0)
            return DesktopIntent(
                tool="social_post",
                parameters=validate_parameters("social_post", raw),
            )
        return None

    # file_copy: "copy <path> to/into <path>" — both sides must be paths.
    if re.match(r"^(?:please\s+)?(?:copy|duplicate)\b", lowered):
        m = re.search(r"\b(?:to|into)\s+", clause, re.IGNORECASE)
        if m:
            source = _find_path(clause[: m.start()])
            destination = _find_path(clause[m.end():])
            if source and destination:
                return DesktopIntent(
                    tool="file_copy",
                    parameters=validate_parameters("file_copy", {"source": source, "destination": destination}),
                )
        return None

    # file ops needing an explicit "file" noun or a path target.
    if re.match(r"^(?:please\s+)?(?:write|create|make|save|put|dump)\b", lowered):
        path = None
        # "to/into/at <path>" first (high confidence), then "[file] named X".
        m_to = re.search(r"\b(?:to|into|at)\s+(?P<p>" + _PATH.pattern + r")", clause, re.IGNORECASE)
        m_named = re.search(r"\b(?:named|called)\s+(?P<p>" + _PATH.pattern + r")", clause, re.IGNORECASE)
        if m_to:
            path = m_to.group("p")
        elif m_named:
            path = m_named.group("p")
        if path:
            content = _quoted(clause) or ""
            return DesktopIntent(
                tool="file_write",
                parameters=validate_parameters("file_write", {"path": path, "content": content}),
            )
        return None

    # file_read: "read/open/view the file <path>" — the path must follow
    # the noun directly, so prose mentions of "file" never match.
    m = re.match(
        r"^(?:please\s+)?(?:read|open|view|load)(?:\s+(?:the|a|this|that)\s+)?\s*(?:file|document)\s+(?:named\s+|called\s+)?(?P<p>" + _PATH.pattern + r")",
        clause, re.IGNORECASE,
    )
    if m:
        return DesktopIntent(
            tool="file_read",
            parameters=validate_parameters("file_read", {"path": m.group("p")}),
        )

    # browser_navigate: an action verb directly followed by a URL.
    if re.match(r"^(?:please\s+)?(?:navigate|go)\s+to\s+" + _URL.pattern, lowered):
        url = _URL.search(clause)
        if url:
            return DesktopIntent(
                tool="browser_navigate",
                parameters=validate_parameters("browser_navigate", {"url": url.group(0)}),
            )

    # desktop_open_app: "open/launch <App>" with a quoted or Capitalised
    # name — "open ... file" is handled above and excluded here. The
    # leading-capital name requirement is what keeps "open my browser" /
    # "open the file" from matching; only a Proper-noun or quoted target
    # is treated as an app name.
    m = re.match(
        r"^(?:[Pp]lease\s+)?(?:[Oo]pen|[Ll]aunch)\s+(?P<q>[A-Z][A-Za-z0-9 _-]{0,30}?)"
        r"(?:\s+(?:the\s+)?(?:app|application)\b|\s+(?:now|please|for me)\b|[.!?]?\s*$)",
        clause,
    )
    if m is None:
        m = re.match(r"^(?:[Pp]lease\s+)?(?:[Oo]pen|[Ll]aunch)\s+(?P<q>\"[^\"]+\"|“[^”]+”)", clause)
    if m and not re.search(r"\bfile\b", lowered):
        name = m.group("q").strip("\"“' ").strip()
        if name:
            return DesktopIntent(
                tool="desktop_open_app",
                parameters=validate_parameters("desktop_open_app", {"name": name}),
            )

    return None


# ---------------------------------------------------------------------------
# Layer 2: optional LLM classifier (strict JSON, NO tool declarations)
# ---------------------------------------------------------------------------

_CLASSIFIER_INSTRUCTION = (
    "You classify whether a chat message requests a local desktop action. "
    "Reply with EXACTLY ONE JSON object and nothing else: either "
    '{"tool": "none", "parameters": {}} or '
    '{"tool": "<one of the listed names>", "parameters": {...}}. '
    "Parameters only ever use the keys path, content, source, destination, "
    "name, url. This request can only ever become a PENDING approval a "
    "human must decide; never state or infer that anything is approved. "
    "Anything that is not an imperative action request is \"none\". "
    "Allowed tools and their parameters: {allowed}"
)


async def classify_with_llm(message: str, service: Any = None) -> DesktopIntent | None:
    """LLM fallback layer. Single text-generation call — this function
    physically cannot invoke a tool: it uses `generate()` (no function
    declarations exist on this path) and validates the reply against the
    protected whitelist with the same `validate_parameters` the heuristic
    uses. Parse failure / unconfigured model → no intent (fails closed)."""
    from services.gemini import GeminiService, is_circuit_open

    gemini = service or GeminiService()
    if not gemini.is_configured() or is_circuit_open():
        return None

    allowed = {
        tool: list(params.keys())
        for tool, params in _ALLOWED_PARAMETERS.items()
        if is_protected(tool)
    }
    reply = await gemini.generate(
        _CLASSIFIER_INSTRUCTION.replace("{allowed}", json.dumps(allowed)),
        message[:4000],
    )
    if not reply:
        return None
    match = re.search(r"\{.*\}", reply, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    tool = str(parsed.get("tool", "")).strip()
    if not tool or tool == "none" or not is_protected(tool):
        return None
    raw = parsed.get("parameters")
    if not isinstance(raw, dict):
        # Malformed parameter payload from the model: fail closed rather
        # than coerce — a pending row with guessed empty parameters has
        # no business appearing in a human's queue.
        return None
    return DesktopIntent(tool=tool, parameters=validate_parameters(tool, raw))


# ---------------------------------------------------------------------------
# Entry point used by the chat route
# ---------------------------------------------------------------------------

async def handle_chat_desktop_request(
    message: str, *, tenant_id: str, actor_key_id: str | None,
    classifier: Any = None,
) -> PendingApprovalInfo | None:
    """Create a pending approval for a chat-requested desktop action — or
    nothing at all. This is the entire capability of the chat path:
    `request_execution`, which by construction never executes, never
    touches the bridge and never reads or writes approval state beyond
    inserting a pending row. Returns None on no-intent and on any failure
    (chat must never break because of this feature)."""
    try:
        intent = detect_desktop_intent(message)
        if intent is None:
            intent = await (classifier or classify_with_llm)(message)
        if intent is None or not is_protected(intent.tool):
            return None

        service = get_approval_service()
        record = service.request_execution(
            tool=intent.tool,
            parameters=intent.parameters,
            tenant_id=tenant_id,
            actor_key_id=actor_key_id,
            title=f"Chat request: {intent.tool}",
        )
        return PendingApprovalInfo(
            approval_id=record.id,
            task_id=record.task_id,
            tool=record.tool,
            status="pending_approval",
            expires_at=record.expires_at,
            requires="human_approval",
            queue_path="/tasks",
        )
    except ApprovalError as exc:
        logger.warning("chat_approval_rejected detail=%s", exc.detail)
        return None
    except Exception:
        logger.warning("chat_approval_failed", exc_info=True)
        return None
