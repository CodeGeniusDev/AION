"""Phase 7 social scaffolding: PKCE, the 0600 vault, and dry-run by default.

What these tests pin down:
- OAuth helpers are spec-correct (S256 PKCE, unguessable state) and the
  TokenVault refuses insecure files — tokens never leak into reprs,
  results or logs;
- the ``social_post`` executor is DRY-RUN unless THIS machine's config
  flips live_enabled AND a real vault token exists — a request
  parameter ("live": true) changes nothing;
- the default path performs zero network I/O (no provider call is even
  built with an auth value), and unknown platforms/missing media fail
  with clear messages instead of crashes.
"""

import base64
import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from aion_desktop.bridge import _executor_for
from aion_desktop.social.oauth import (
    TokenSet,
    TokenVault,
    TokenVaultError,
    build_authorize_url,
    generate_pkce,
    generate_state,
)
from aion_desktop.social.providers import PROVIDERS, SocialProvider

WS = Path("/tmp/aion-test-ws")


def _social_exec(vault_dir: str, live_enabled: bool = False, **params):
    executor = _executor_for(
        "social_post", WS, [WS],
        social={"live_enabled": live_enabled, "oauth_dir": str(vault_dir)},
    )
    assert executor is not None
    result = executor(params)
    # The social executor is async — bridge awaits coroutines; drive it here.
    import asyncio
    if hasattr(result, "__await__"):
        result = asyncio.run(result)
    return result


# ---------------------------------------------------------------------------
# OAuth primitives
# ---------------------------------------------------------------------------

def test_pkce_matches_rfc7636_s256_definition() -> None:
    verifier, challenge = generate_pkce()
    # 43–128 chars, unreserved set (RFC 7636 §4.1)
    assert 43 <= len(verifier) <= 128
    assert set(verifier) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert challenge == expected


def test_pkce_and_state_are_fresh_per_call() -> None:
    assert generate_pkce()[0] != generate_pkce()[0]
    assert generate_state() != generate_state()
    assert len(generate_state()) >= 32


def test_authorize_url_uses_s256_and_state() -> None:
    url = build_authorize_url(
        authorize_endpoint="https://api.example/oauth",
        client_id="cid", redirect_uri="http://localhost:8989/cb",
        scopes=["a", "b"], state="st", code_challenge="ch",
    )
    assert "code_challenge_method=S256" in url
    assert "state=st" in url and "scope=a+b" in url  # space-joined scopes


def test_authorize_url_requires_client_id() -> None:
    with pytest.raises(ValueError):
        build_authorize_url(
            authorize_endpoint="https://x", client_id="",
            redirect_uri="http://localhost:1/cb", scopes=[],
            state="s", code_challenge="c",
        )


# ---------------------------------------------------------------------------
# Token vault — permissions are the product
# ---------------------------------------------------------------------------

def test_vault_writes_owner_only_file(tmp_path) -> None:
    vault = TokenVault(tmp_path / ".aion")
    target = vault.store("meta", TokenSet(access_token="SECRET-VALUE", scopes=["x"]))
    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600, f"expected 0600, got {mode:04o}"
    loaded = vault.get("meta")
    assert loaded is not None and loaded.access_token == "SECRET-VALUE"


def test_vault_refuses_loose_permissions_and_symlinks(tmp_path) -> None:
    vault = TokenVault(tmp_path)
    vault.store("pinterest", TokenSet(access_token="t"))
    target = vault._token_file("pinterest")
    os.chmod(target, 0o644)
    with pytest.raises(TokenVaultError):
        vault.get("pinterest")

    link_dir = tmp_path / "v2"
    link_dir.mkdir()
    vault2 = TokenVault(link_dir)
    real = tmp_path / "elsewhere.json"
    real.write_text('{"access_token": "x"}')
    (link_dir / "tiktok.json").symlink_to(real)
    with pytest.raises(TokenVaultError):
        vault2.get("tiktok")
    # And store refuses to write *through* a symlink (O_TRUNC hazard):
    with pytest.raises(TokenVaultError):
        vault2.store("tiktok", TokenSet(access_token="y"))


def test_vault_relative_path_anchors_to_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    vault = TokenVault(".aion")
    assert vault.root == tmp_path / ".aion"


def test_tokenset_repr_never_leaks() -> None:
    tokens = TokenSet(access_token="SUPER-SECRET", refresh_token="ALSO-SECRET")
    assert "SUPER-SECRET" not in repr(tokens)
    assert "ALSO-SECRET" not in repr(tokens)


# ---------------------------------------------------------------------------
# social_post executor — dry-run by construction
# ---------------------------------------------------------------------------

def test_facebook_dry_run_previews_without_secrets(tmp_path) -> None:
    result = _social_exec(tmp_path, platform="facebook", content="Hello AION")
    assert result["success"] is True and result["mode"] == "dry_run"
    preview = result["request_preview"]
    assert preview["method"] == "POST" and preview["url"].endswith("/feed")
    assert "graph.facebook.com" in preview["url"]
    assert preview["content_preview"] == "Hello AION"
    assert result["credentials"] == {"client_id_configured": False, "token_in_vault": False}
    dumped = json.dumps(result).lower()
    for leak in ("access_token", "client_secret", "bearer", "super-secret"):
        assert leak not in dumped


def test_request_params_cannot_flip_live_mode(tmp_path, monkeypatch) -> None:
    """A spoofed 'live' parameter is ignored; even with config live_enabled
    the gate stays shut without BOTH a client secret env and a vault
    token. Only the triple gate opens post_live — and we prove the
    executor reaches it only then, with no network available."""
    calls = []

    async def fake_post_live(self, content, media_url, vault):
        calls.append(self.spec.platform)
        return {"success": True, "mode": "live", "platform": self.spec.platform}

    monkeypatch.setattr(SocialProvider, "post_live", fake_post_live)

    # 1. live param, config OFF → dry-run, post_live never called.
    result = _social_exec(tmp_path, platform="facebook", content="hi", live=True)
    assert result["mode"] == "dry_run" and calls == []

    # 2. config ON but no secret env and no token → still dry-run.
    result = _social_exec(tmp_path, live_enabled=True, platform="facebook", content="hi")
    assert result["mode"] == "dry_run" and calls == []

    # 3. config ON + secret env + vault token → gate opens (approved
    #    upstream by the ledger; this test never grants network access).
    monkeypatch.setenv("AION_SOCIAL_META_CLIENT_SECRET", "unit-test-secret")
    TokenVault(tmp_path).store("meta", TokenSet(access_token="t", scopes=["pages_manage_posts"]))
    result = _social_exec(tmp_path, live_enabled=True, platform="facebook", content="hi")
    assert result["mode"] == "live" and calls == ["facebook"]


def test_unknown_platform_fails_cleanly(tmp_path) -> None:
    result = _social_exec(tmp_path, platform="twitter", content="hi")
    assert result["success"] is False
    assert "Unsupported platform" in result["error"]
    assert "facebook" in result["error"]  # tells you what IS supported


def test_empty_content_refused(tmp_path) -> None:
    result = _social_exec(tmp_path, platform="facebook", content="   ")
    assert result["success"] is False and "must not be empty" in result["error"]


@pytest.mark.parametrize("platform,media_kind", [("pinterest", "image"), ("tiktok", "video")])
def test_media_required_platforms(tmp_path, platform, media_kind) -> None:
    result = _social_exec(tmp_path, platform=platform, content="hi")
    assert result["success"] is False and media_kind in result["error"]
    with_media = _social_exec(
        tmp_path, platform=platform, content="hi",
        media_url=f"https://cdn.example/a.{'png' if media_kind == 'image' else 'mp4'}",
    )
    assert with_media["success"] is True and with_media["mode"] == "dry_run"


def test_dry_run_never_touches_the_network(tmp_path, monkeypatch) -> None:
    """Hard proof: sockets are disabled for this test; every platform
    still dry-runs successfully — zero network I/O by construction."""
    import socket

    def no_network(*a, **k):
        raise AssertionError("dry-run must not open a socket")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    for platform, media in (("facebook", None), ("instagram", "https://cdn.example/a.png"),
                            ("pinterest", "https://cdn.example/a.png"),
                            ("tiktok", "https://cdn.example/a.mp4")):
        result = _social_exec(tmp_path, platform=platform, content="hi", media_url=media or "")
        assert result["mode"] == "dry_run", platform


def test_provider_registry_covers_only_official_platforms() -> None:
    assert set(PROVIDERS) == {"facebook", "instagram", "pinterest", "tiktok"}
    for provider in PROVIDERS.values():
        assert provider.spec.authorize_url.startswith("https://")
        assert provider.spec.token_url.startswith("https://")
