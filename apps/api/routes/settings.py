"""Workspace settings endpoints.

Backed by the profile SQLite store (same database): PUT /api/settings
survives restarts. GET falls back to model defaults when nothing has
been saved yet, preserving the original response contract exactly.
"""

from fastapi import APIRouter

from memory.profile_store import get_default_profile_store
from models.settings import AppSettings

router = APIRouter(tags=["settings"])


def _load() -> AppSettings:
    raw = get_default_profile_store().get_settings_json()
    if raw is None:
        return AppSettings()
    try:
        return AppSettings.model_validate_json(raw)
    except ValueError:
        # A model change can make an old snapshot unparseable; degrade to
        # defaults instead of 500-ing the settings screen.
        return AppSettings()


@router.get("/settings", response_model=AppSettings)
async def get_settings() -> AppSettings:
    current = _load()
    # Legacy "dim" preference is surfaced as the canonical "dark" theme.
    if current.theme == "dim":
        return current.model_copy(update={"theme": "dark"})
    return current


@router.put("/settings", response_model=AppSettings)
async def update_settings(payload: AppSettings) -> AppSettings:
    # Accept legacy "dim" writes but persist them as "dark" going forward.
    if payload.theme == "dim":
        payload = payload.model_copy(update={"theme": "dark"})
    get_default_profile_store().set_settings_json(payload.model_dump_json())
    return payload
