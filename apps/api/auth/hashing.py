"""API key generation and hashing.

API keys are high-entropy, randomly generated tokens (32 bytes via
`secrets.token_urlsafe`) — not human-chosen passwords. A straightforward
salted-by-entropy SHA-256 hash is standard, appropriate practice here. This
is deliberately NOT a slow password-hashing KDF (bcrypt/scrypt/argon2):
those exist to resist offline brute-forcing of a LOW-entropy human-chosen
secret. A 256-bit random API key has no such weakness — the only purpose
of hashing it is to avoid storing the literal secret at rest, so a fast
cryptographic hash is the correct tool, not the wrong one.
"""

import hashlib
import hmac
import secrets


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, hashed_key: str) -> bool:
    """Constant-time comparison to avoid timing side-channels."""
    return hmac.compare_digest(hash_api_key(raw_key), hashed_key)
