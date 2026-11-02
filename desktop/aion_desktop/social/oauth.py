"""OAuth2 scaffolding for the social providers (Phase 7).

Two honest guarantees, both tested:

* PKCE + state are built per RFC 7636 / OAuth 2.1 BCP — S256 only, no
  plaintext challenge, single-use state strings.
* Tokens live only in the vault (``~/.aion`` by default) as 0600 JSON
  files. The vault refuses world/group-readable files and symlinks, and
  no token-bearing object ever appears in logs or tool results: the
  dataclass reprs are redacted.

Nothing here performs a network call. The authorize-URL builder is pure;
the token exchange is a code path that the triple gate (config,
approval, real token request) never reaches in this build.
"""

import base64
import hashlib
import os
import secrets
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

# Vault files holding OAuth tokens. Anything looser than owner-only
# rw/rwx on the OWNER bits is refused — group/world bits must be zero.
_TOKEN_FILE_MODE = 0o600


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_pkce() -> tuple[str, str]:
    """Return (verifier, S256 challenge) per RFC 7636 §4.2/§4.3."""
    verifier = _b64url(secrets.token_bytes(32))  # 43 chars, in spec range
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def generate_state() -> str:
    """CSRF state for the authorize redirect. Single-use, unguessable."""
    return secrets.token_urlsafe(32)


def build_authorize_url(
    *,
    authorize_endpoint: str,
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    state: str,
    code_challenge: str,
) -> str:
    """Pure authorize-URL builder. Empty client_id is a configuration
    error we surface early instead of sending the browser nowhere."""
    if not client_id:
        raise ValueError("client_id is required to build an authorize URL")
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{authorize_endpoint}?{urlencode(params)}"


@dataclass
class TokenSet:
    """One provider's stored tokens. NEVER log this object; repr is
    redacted so an accidental f-string cannot leak a token."""

    access_token: str = field(repr=False, default="")
    refresh_token: str = field(repr=False, default="")
    expires_at: str = ""  # ISO-8601, owner-parsed; empty = unknown
    scopes: list[str] = field(default_factory=list)

    def __repr__(self) -> str:  # redaction is structural, not opt-in
        return f"TokenSet(scopes={self.scopes!r}, expires_at={self.expires_at!r})"

    def as_dict(self) -> dict[str, Any]:
        # Only ever written to the 0600 vault file — never to a result,
        # an audit row or a log line.
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scopes": self.scopes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenSet":
        return cls(
            access_token=str(data.get("access_token", "")),
            refresh_token=str(data.get("refresh_token", "")),
            expires_at=str(data.get("expires_at", "")),
            scopes=[str(s) for s in data.get("scopes", [])],
        )


class TokenVaultError(RuntimeError):
    pass


class TokenVault:
    """0600 JSON token store under ``oauth_dir`` (home-anchored).

    The vault is the ONLY reader/writer of token material. Dry-run code
    paths call ``get()`` to check existence — they never receive the
    secret itself unless a live, approved, config-enabled post runs.
    """

    def __init__(self, oauth_dir: str | Path) -> None:
        path = Path(str(oauth_dir)).expanduser()
        if not path.is_absolute():
            # A relative vault would anchor tokens to whatever CWD the
            # bridge started in. Anchor to home, always.
            path = Path.home() / path
        self.root = path

    def _token_file(self, provider: str) -> Path:
        safe = provider.replace("/", "_")
        return self.root / f"{safe}.json"

    def get(self, provider: str) -> TokenSet | None:
        """Load a provider's tokens, or None. Refuses unsafe files —
        a silently-insecure token file is worse than a missing one."""
        target = self._token_file(provider)
        if not target.exists():
            return None
        if target.is_symlink():
            raise TokenVaultError(
                f"Token file for '{provider}' is a symlink — refusing to read it."
            )
        mode = stat.S_IMODE(target.stat().st_mode)
        if mode & 0o077:
            raise TokenVaultError(
                f"Token file for '{provider}' is group/world accessible "
                f"(mode {mode:04o}) — chmod 600 it or delete it."
            )
        import json
        try:
            return TokenSet.from_dict(json.loads(target.read_text()))
        except (ValueError, OSError) as exc:
            raise TokenVaultError(f"Unreadable token file for '{provider}': {exc}") from exc

    def store(self, provider: str, tokens: TokenSet) -> Path:
        """Write 0600 from the first byte — never create-then-chmod."""
        import json
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        target = self._token_file(provider)
        # O_TRUNC follows symlinks — never write through one.
        if target.is_symlink():
            raise TokenVaultError(
                f"Token file for '{provider}' is a symlink — refusing to overwrite."
            )
        payload = json.dumps(tokens.as_dict(), indent=2).encode()
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _TOKEN_FILE_MODE)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        return target

    def delete(self, provider: str) -> bool:
        target = self._token_file(provider)
        if target.exists() and not target.is_symlink():
            target.unlink()
            return True
        return False
