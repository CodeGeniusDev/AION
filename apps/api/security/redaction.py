"""Phase 1F: Secret Guard — detect credentials in chat input.

The request boundary (routes/chat.py) calls redact_text() BEFORE the
message reaches the conversation store, the workflow runner (Gemini
prompt, agents, cognitive bus, memory consolidation), the chat-driven
approval hook or alert previews. The raw value therefore never exists
downstream of this module: what is persisted, logged and sent to the
model is the redacted version, e.g. "[REDACTED: password]".

Design constraints:
- Detection requires an actual secret-shaped VALUE, never a bare word.
  "explain password reset flow" and "use a strong password" must stay
  untouched (they are ordinary support questions).
- Patterns run in a fixed order: structural blocks (private keys) →
  specific key formats (Bearer, AIza…, sk-…) → generic keyword=value →
  entropy candidates (long hex/base64) → Luhn-validated card numbers.
  Earlier patterns consume what later ones would partially match, so a
  secret is never half-redacted.
"""

import re
from dataclasses import dataclass

# Keyword=value: "password: hunter2", "pwd=hunter2", "my password is
# hunter2". "is" as a separator is reserved for password-shaped words —
# "secret is out" is an idiom, not a credential. The value must contain
# at least one non-space character.
_KEYWORD_RE = re.compile(
    r"(?i)\b(?:"
    # "password: x", "pwd=x", "my password is x" — "is" allowed for
    # password-shaped words only.
    r"(?:password|passwd|passphrase|pwd)(?:\s+is|\s*[:=])"
    # "secret: x", "api_key=x", "access token: x" — explicit separator
    # required, so the idiom "my secret is out" stays untouched.
    r"|(?:secret|api[\s_-]*key|access[\s_-]*token)\s*[:=]"
    r")\s*"
    r"([^\s'\",;:]+)"
)
# Authorization header style bearer tokens.
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]{8,}=*")
# Known provider key formats.
_GOOGLE_KEY_RE = re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")
_PREFIXED_KEY_RE = re.compile(r"\bsk-(?:live-|test-|proj-)?[A-Za-z0-9_\-]{16,}")
# PEM private key blocks (with or without header/footer).
_PEM_RE = re.compile(
    r"-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH|PGP|ENCRYPTED)?\s*PRIVATE\s+KEY(?:\s+BLOCK)?-----"
    r"(?:.*?-----END\s+(?:RSA|EC|DSA|OPENSSH|PGP|ENCRYPTED)?\s*PRIVATE\s+KEY(?:\s+BLOCK)?-----)?"
    r"|MII[A-Za-z0-9/+]{40,}",
    re.DOTALL,
)
# Long opaque hex or base64 blobs (session tokens, hashes, signatures).
_HEX_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b")
# \b fails before '=' padding (both word chars) — assert the blob ends
# at a non-base64 character instead.
_B64_RE = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/=])")
# Candidate card numbers: 13-19 digits, optionally separated in groups.
_CARD_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")


def _luhn_valid(digits: str) -> bool:
    total = 0
    reverse = digits[::-1]
    for index, char in enumerate(reverse):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


@dataclass(frozen=True)
class RedactionResult:
    text: str
    labels: tuple[str, ...]

    @property
    def redacted(self) -> bool:
        return len(self.labels) > 0


def _apply(pattern: re.Pattern[str], label: str, text: str, groups: dict[str, int], value_group: int | None = None) -> str:
    def replace(match: re.Match[str]) -> str:
        groups[label] = groups.get(label, 0) + 1
        # Keyword pattern captures only the VALUE — keep the benign
        # keyword ("password:") so the user can see what happened.
        if value_group is not None and match.group(value_group) is not None:
            head = match.string[match.start() : match.start(value_group)]
            return f"{head}[REDACTED: {label}]"
        return f"[REDACTED: {label}]"

    return pattern.sub(replace, text)


# Stable warning order — independent of which pattern ran first — so
# clients always see the same sequence for the same set of secrets.
_LABEL_ORDER = ("password", "API key", "private key", "bearer token", "secret", "card number")


def redact_text(text: str) -> RedactionResult:
    """Return text with every detected credential replaced by a
    [REDACTED: kind] marker, plus the ordered list of kinds found."""
    if not text:
        return RedactionResult(text=text, labels=())

    groups: dict[str, int] = {}
    redacted = text

    # Structural / specific formats first — the generic keyword pattern
    # would otherwise consume e.g. "Bearer" as a secret word.
    redacted = _apply(_PEM_RE, "private key", redacted, groups)
    redacted = _apply(_GOOGLE_KEY_RE, "API key", redacted, groups)
    redacted = _apply(_PREFIXED_KEY_RE, "API key", redacted, groups)
    redacted = _apply(_BEARER_RE, "bearer token", redacted, groups)

    # Generic keyword=value (password:, passwd , pwd=, "my password is"…).
    redacted = _apply(_KEYWORD_RE, "password", redacted, groups, value_group=1)

    # Entropy candidates. A base64 blob is only a candidate when it does
    # not look like ordinary mixed-case prose compressed (no lowercase
    # runs of more than 5 letters, e.g. "thequickbrown…").
    def _candidate_b64(match: re.Match[str]) -> bool:
        value = match.group()
        return not re.search(r"[a-z]{6}", value)

    redacted = _apply(_HEX_RE, "secret", redacted, groups)
    remaining = []
    cursor = 0
    for match in _B64_RE.finditer(redacted):
        if _candidate_b64(match):
            remaining.append(match)
    if remaining:
        parts: list[str] = []
        for match in remaining:
            parts.append(redacted[cursor : match.start()])
            groups["secret"] = groups.get("secret", 0) + 1
            parts.append("[REDACTED: secret]")
            cursor = match.end()
        parts.append(redacted[cursor:])
        redacted = "".join(parts)

    # Card numbers: Luhn-validated, so arbitrary long digit strings
    # (IDs, phone numbers, quantities) stay untouched.
    def _replace_card(match: re.Match[str]) -> str:
        digits = re.sub(r"[ -]", "", match.group())
        if not (13 <= len(digits) <= 19) or not _luhn_valid(digits):
            return match.group()
        groups["card number"] = groups.get("card number", 0) + 1
        return "[REDACTED: card number]"

    redacted = _CARD_RE.sub(_replace_card, redacted)

    # Deterministic canonical order of the kinds found.
    labels = tuple(label for label in _LABEL_ORDER if label in groups)
    return RedactionResult(text=redacted, labels=labels)
