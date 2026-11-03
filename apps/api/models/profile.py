"""Profile data model (Phase 1D).

Single-tenant workspace identity. Validation mirrors the UI contract:
display_name 1-60, username slug, optional RFC-ish email, IANA timezone,
bio <= 200, avatar_color restricted to the preset palette (initials
avatar only — there is deliberately no file-upload field).
"""

import re
from zoneinfo import available_timezones

from pydantic import BaseModel, Field, field_validator

# Preset palette keys; the frontend maps each to real CSS tokens.
AVATAR_COLORS = ("navy", "blue", "teal", "violet", "amber", "rose")

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


class Profile(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)
    username: str = ""
    email: str = ""
    role: str = Field(default="", max_length=60)
    timezone: str = "UTC"
    bio: str = Field(default="", max_length=200)
    avatar_color: str = "navy"

    @field_validator("display_name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("display_name cannot be blank")
        return v.strip()

    @field_validator("username")
    @classmethod
    def _username_slug(cls, v: str) -> str:
        if not v:
            return v  # empty → derived from display_name in the route
        if len(v) > 30 or not _SLUG_RE.match(v):
            raise ValueError(
                "username must be a slug: lowercase letters, digits and hyphens"
            )
        return v

    @field_validator("email")
    @classmethod
    def _email_optional_valid(cls, v: str) -> str:
        v = v.strip()
        if v and (len(v) > 254 or not _EMAIL_RE.match(v)):
            raise ValueError("email is not valid")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz_is_IANA(cls, v: str) -> str:
        if v not in available_timezones():
            raise ValueError("timezone must be a valid IANA zone (e.g. Asia/Dubai)")
        return v

    @field_validator("avatar_color")
    @classmethod
    def _color_in_palette(cls, v: str) -> str:
        if v not in AVATAR_COLORS:
            raise ValueError(f"avatar_color must be one of {AVATAR_COLORS}")
        return v


class ProfileResponse(BaseModel):
    """GET /api/profile envelope. `configured` is false until the first save."""

    configured: bool
    profile: Profile | None = None
    created_at: str | None = None
    updated_at: str | None = None
