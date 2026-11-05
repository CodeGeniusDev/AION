"""Social provider scaffolding — official APIs only (Phase 7).

Every provider here maps to a documented, official posting endpoint:

* Facebook — Graph API ``/{page-id}/feed``
* Instagram — Graph API content publishing (container create → publish);
  requires a Business/Creator account and the reviewed
  ``instagram_content_publish`` permission.
* Pinterest — v5 API ``/v5/boards/{board-id}/pins``
* TikTok — Content Posting API ``/v2/post/`` (DIRECT_PUBLIC_POST requires
  an app that passed review; unreviewed apps can only upload as private).

The design rule mirrors the rest of the bridge: **config decides, never
the request.** A tool call carries only ``platform`` + ``content``;
live-vs-dry-run is this machine's ``social.live_enabled`` plus the
approval gate, and credentials come only from env vars and the 0600
token vault. No passwords, no scraping, no unofficial endpoints.
"""

import os
from dataclasses import dataclass, field
from typing import Any

from .oauth import TokenVault


@dataclass(frozen=True)
class ProviderSpec:
    platform: str
    display_name: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    client_id_env: str
    client_secret_env: str
    vault_key: str  # one vault file can serve two platforms (Meta)
    requires_media: str | None = None  # "image" | "video" | None
    owner_notes: str = ""


@dataclass(frozen=True)
class SocialRequest:
    """The exact official-API call a live post would make. Auth material
    is NEVER part of this object — headers carry a ``<ACCESS_TOKEN>``
    placeholder so previews stay secret-free."""

    method: str
    url: str
    payload: dict[str, Any] = field(default_factory=dict)
    header_names: tuple[str, ...] = ("Authorization", "Content-Type")


class SocialProvider:
    """Interface: validate → build request → (dry-run preview | live send).

    Subclasses fill the spec and the request builder. Nothing in this
    class touches the network; ``post_live`` is the single seam and is
    only reachable behind the bridge's triple gate.
    """

    def __init__(self, spec: ProviderSpec) -> None:
        self.spec = spec

    # -- validation ------------------------------------------------------
    def validate(self, content: str, media_url: str | None) -> str | None:
        """Return a human-readable refusal, or None when postable."""
        if not content.strip():
            return "Post content must not be empty."
        if self.spec.requires_media == "image" and not media_url:
            return (
                f"{self.spec.display_name} posting requires an image URL "
                "(official API requirement) — none was provided."
            )
        if self.spec.requires_media == "video" and not media_url:
            return (
                f"{self.spec.display_name} posting requires a video URL "
                "(official API requirement) — none was provided."
            )
        return None

    # -- request building ------------------------------------------------
    def build_request(self, content: str, media_url: str | None) -> SocialRequest:
        raise NotImplementedError

    def dry_run(self, content: str, media_url: str | None, vault: TokenVault) -> dict[str, Any]:
        """Secret-free preview of exactly what a live post would send,
        plus the real credential state so the owner knows what is
        missing. Performs no network I/O."""
        request = self.build_request(content, media_url)
        client_id = os.environ.get(self.spec.client_id_env, "")
        try:
            token_present = vault.get(self.spec.vault_key) is not None
        except Exception:
            # A corrupt/insecure vault file must not leak through here;
            # the preview only needs to know a token is unusable.
            token_present = False
        return {
            "success": True,
            "mode": "dry_run",
            "platform": self.spec.platform,
            "request_preview": {
                "method": request.method,
                "url": request.url,
                "payload_keys": sorted(request.payload.keys()),
                "content_preview": content[:120],
            },
            "credentials": {
                "client_id_configured": bool(client_id),
                "token_in_vault": token_present,
            },
            "owner_notes": self.spec.owner_notes,
        }

    def live_gate_open(self, live_enabled: bool, vault: TokenVault) -> bool:
        """Live posting needs config AND a vault token AND (by the
        bridge's design) an already-consumed human approval. The
        approval happened upstream; this checks the local two."""
        if not live_enabled:
            return False
        if not os.environ.get(self.spec.client_secret_env):
            return False
        return vault.get(self.spec.vault_key) is not None

    async def post_live(self, content: str, media_url: str | None, vault: TokenVault) -> dict[str, Any]:
        """The ONLY network seam. Sends the built request with the
        vault token. Kept deliberately thin and never exercised in
        tests or in this session's builds."""
        import aiohttp

        tokens = vault.get(self.spec.vault_key)
        if tokens is None:
            return {"success": False, "error": "No OAuth token in the vault for this provider."}
        request = self.build_request(content, media_url)
        headers = {"Authorization": f"Bearer {tokens.access_token}"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                if request.method == "POST":
                    async with session.post(request.url, json=request.payload, headers=headers) as resp:
                        body = await resp.json(content_type=None)
                else:  # pragma: no cover - Graph API page posts are form-encoded POSTs
                    async with session.get(request.url, headers=headers) as resp:
                        body = await resp.json(content_type=None)
        except Exception as exc:
            # Exception text can contain URLs but never our token: aiohttp
            # errors carry the request headers, so we keep only the type.
            return {"success": False, "error": f"Provider request failed: {type(exc).__name__}"}
        return {"success": True, "mode": "live", "platform": self.spec.platform, "response": body}


# ---------------------------------------------------------------------------
# Concrete providers (official endpoints only)
# ---------------------------------------------------------------------------

class FacebookPageProvider(SocialProvider):
    """Meta Graph API — publish to a Facebook Page feed.

    Page access tokens are long-lived and scoped; posting as a PERSON
    via the feed API was retired by Meta years ago and is not attempted.
    """

    def __init__(self) -> None:
        super().__init__(ProviderSpec(
            platform="facebook",
            display_name="Facebook Page",
            authorize_url="https://www.facebook.com/v21.0/dialog/oauth",
            token_url="https://graph.facebook.com/v21.0/oauth/access_token",
            scopes=("pages_manage_posts", "pages_read_engagement"),
            client_id_env="AION_SOCIAL_META_CLIENT_ID",
            client_secret_env="AION_SOCIAL_META_CLIENT_SECRET",
            vault_key="meta",
            owner_notes=(
                "Create a Meta app + a Facebook Page, generate a Page access "
                "token with pages_manage_posts, and set the page id in "
                "AION_SOCIAL_FB_PAGE_ID."
            ),
        ))

    def build_request(self, content: str, media_url: str | None) -> SocialRequest:
        page_id = os.environ.get("AION_SOCIAL_FB_PAGE_ID", "<PAGE_ID>")
        return SocialRequest(
            method="POST",
            url=f"https://graph.facebook.com/v21.0/{page_id}/feed",
            payload={"message": content},
        )


class InstagramProvider(SocialProvider):
    """Meta Graph API — Instagram content publishing (image+caption).

    Real flow is create-media-container → publish; the scaffold builds
    the container-creation request, which is where validation and app
    review actually bite."""

    def __init__(self) -> None:
        super().__init__(ProviderSpec(
            platform="instagram",
            display_name="Instagram Business",
            authorize_url="https://www.facebook.com/v21.0/dialog/oauth",
            token_url="https://graph.facebook.com/v21.0/oauth/access_token",
            scopes=("instagram_content_publish",),
            client_id_env="AION_SOCIAL_META_CLIENT_ID",
            client_secret_env="AION_SOCIAL_META_CLIENT_SECRET",
            vault_key="meta",
            requires_media="image",
            owner_notes=(
                "Needs an IG Business/Creator account linked to a FB Page and "
                "app review for instagram_content_publish. Set "
                "AION_SOCIAL_IG_USER_ID."
            ),
        ))

    def build_request(self, content: str, media_url: str | None) -> SocialRequest:
        ig_user = os.environ.get("AION_SOCIAL_IG_USER_ID", "<IG_USER_ID>")
        return SocialRequest(
            method="POST",
            url=f"https://graph.facebook.com/v21.0/{ig_user}/media",
            payload={"caption": content, "image_url": media_url or ""},
        )


class PinterestProvider(SocialProvider):
    """Pinterest API v5 — create a pin on a board."""

    def __init__(self) -> None:
        super().__init__(ProviderSpec(
            platform="pinterest",
            display_name="Pinterest",
            authorize_url="https://api.pinterest.com/oauth/",
            token_url="https://api.pinterest.com/v5/oauth/token",
            scopes=("board_access", "pins:write"),
            client_id_env="AION_SOCIAL_PINTEREST_CLIENT_ID",
            client_secret_env="AION_SOCIAL_PINTEREST_CLIENT_SECRET",
            vault_key="pinterest",
            requires_media="image",
            owner_notes=(
                "Create a Pinterest developer app, request pins:write + "
                "board_access, and set AION_SOCIAL_PINTEREST_BOARD_ID."
            ),
        ))

    def build_request(self, content: str, media_url: str | None) -> SocialRequest:
        board_id = os.environ.get("AION_SOCIAL_PINTEREST_BOARD_ID", "<BOARD_ID>")
        return SocialRequest(
            method="POST",
            url=f"https://api.pinterest.com/v5/boards/{board_id}/pins",
            payload={"note": content, "media_source": {"link": media_url or ""}},
        )


class TikTokProvider(SocialProvider):
    """TikTok Content Posting API — direct post endpoint.

    PUBLIC direct posting requires an app that passed TikTok review;
    until then the same endpoint posts privately. Flagged in notes."""

    def __init__(self) -> None:
        super().__init__(ProviderSpec(
            platform="tiktok",
            display_name="TikTok",
            authorize_url="https://www.tiktok.com/v2/auth/authorize/",
            token_url="https://open.tiktokapis.com/v2/oauth/token/",
            scopes=("video.publish",),
            client_id_env="AION_SOCIAL_TIKTOK_CLIENT_ID",
            client_secret_env="AION_SOCIAL_TIKTOK_CLIENT_SECRET",
            vault_key="tiktok",
            requires_media="video",
            owner_notes=(
                "Content Posting API requires app review before DIRECT_PUBLIC_POST; "
                "unreviewed apps post privately only."
            ),
        ))

    def build_request(self, content: str, media_url: str | None) -> SocialRequest:
        return SocialRequest(
            method="POST",
            url="https://open.tiktokapis.com/v2/post/publish/video_async/",
            payload={
                "post_info": {"title": content, "visibility": "PUBLIC"},
                "source_info": {"source": "PULL_FROM_URL", "video_url": media_url or ""},
            },
        )


PROVIDERS: dict[str, SocialProvider] = {
    "facebook": FacebookPageProvider(),
    "instagram": InstagramProvider(),
    "pinterest": PinterestProvider(),
    "tiktok": TikTokProvider(),
}


def get_provider(platform: str) -> SocialProvider | None:
    return PROVIDERS.get(platform.strip().lower())
