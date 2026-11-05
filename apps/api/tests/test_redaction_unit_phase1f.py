"""Phase 1F: Secret Guard — detection table.

>= 25 table-driven cases (26 redaction hits + 13 required false
positives). A credential is detected only when a secret-shaped VALUE is
present; ordinary mentions like "explain password reset flow" or "use a
strong password" must stay byte-for-byte untouched.
"""

import pytest

from security.redaction import redact_text

# (input, expected exact output, expected labels) — every case must
# redact the value while keeping the benign keyword where present.
HIT_CASES = [
    ("password: hunter2", "password: [REDACTED: password]", ("password",)),
    ("Password:hunter2", "Password:[REDACTED: password]", ("password",)),
    ("my password is letmein", "my password is [REDACTED: password]", ("password",)),
    ("my passwd is swordfish!1", "my passwd is [REDACTED: password]", ("password",)),
    ("pwd=abc123", "pwd=[REDACTED: password]", ("password",)),
    ("PWD=abc123", "PWD=[REDACTED: password]", ("password",)),
    ("passphrase is corr3ct-horse", "passphrase is [REDACTED: password]", ("password",)),
    ("secret: hunter2", "secret: [REDACTED: password]", ("password",)),
    ("api key: ABCD-1234-efgh", "api key: [REDACTED: password]", ("password",)),
    ("api_key=abcd1234", "api_key=[REDACTED: password]", ("password",)),
    ("access token=abc123def", "access token=[REDACTED: password]", ("password",)),
    (
        "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.abcdefgh",
        "Authorization: [REDACTED: bearer token]",
        ("bearer token",),
    ),
    (
        "use this AIzaSyA1234567890abcdefghijklmnopqrstuv",
        "use this [REDACTED: API key]",
        ("API key",),
    ),
    (
        "key sk-live-abcdef1234567890abcdef1234567890 revoked",
        "key [REDACTED: API key] revoked",
        ("API key",),
    ),
    (
        "sk-proj-ZZZ1234567890abcdefghijklmno",
        "[REDACTED: API key]",
        ("API key",),
    ),
    (
        "here:\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAxyz\n-----END RSA PRIVATE KEY-----\nthanks",
        "here:\n[REDACTED: private key]\nthanks",
        ("private key",),
    ),
    (
        "just the header -----BEGIN PRIVATE KEY-----",
        "just the header [REDACTED: private key]",
        ("private key",),
    ),
    (
        "legacy key MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7U",
        "legacy key [REDACTED: private key]",
        ("private key",),
    ),
    (
        "hash 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08 done",
        "hash [REDACTED: secret] done",
        ("secret",),
    ),
    (
        "blob UERHxSWdNhMLKfZQvsTprOWQxUVBnMlRob0FBQ0FRQT09 attached",
        "blob [REDACTED: secret] attached",
        ("secret",),
    ),
    ("card 4111 1111 1111 1111 expires", "card [REDACTED: card number] expires", ("card number",)),
    ("4539-1488-0343-6467", "[REDACTED: card number]", ("card number",)),
    ("4539148803436467", "[REDACTED: card number]", ("card number",)),
    ("amex 378282246310005 please", "amex [REDACTED: card number] please", ("card number",)),
    (
        "login is user bob password: hunter2 then card 4111 1111 1111 1111",
        "login is user bob password: [REDACTED: password] then card [REDACTED: card number]",
        ("password", "card number"),
    ),
    (
        "password: hunter2 with Bearer aBcDeFgHiJkLmNoP",
        "password: [REDACTED: password] with [REDACTED: bearer token]",
        ("password", "bearer token"),
    ),
]

# Required false positives: the word alone is never a credential.
KEEP_CASES = [
    "explain password reset flow",
    "use a strong password",
    "how do I change my passwd in linux",
    "reset my pwd please",
    "what is a passphrase and how does it work",
    "my secret is out",
    "how do I rotate my api keys safely",
    "Bearer tokens are used in OAuth — what for?",
    "order 123456789012345678 shipped yesterday",  # 18 digits, Luhn-invalid
    "the card was declined, error code 400005 400005 400005",
    "generate a password for me",
    "where do I store my password safely",
    "please reset my password for me",
]


@pytest.mark.parametrize(("text", "expected", "labels"), HIT_CASES)
def test_redaction_hits(text: str, expected: str, labels: tuple) -> None:
    result = redact_text(text)
    assert result.text == expected
    assert result.labels == labels
    assert result.redacted


@pytest.mark.parametrize("text", KEEP_CASES)
def test_redaction_keeps_benign_text(text: str) -> None:
    result = redact_text(text)
    assert result.text == text
    assert not result.redacted


def test_table_covers_minimum_cases() -> None:
    assert len(HIT_CASES) + len(KEEP_CASES) >= 25


def test_never_redacts_a_bare_secret_word() -> None:
    # A trailing keyword with no value must survive untouched.
    assert redact_text("here is the password:").text == "here is the password:"
