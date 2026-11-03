"""Workspace settings endpoints.

In-memory, process-lifetime storage. GET returns the current settings, PUT
replaces them. No authentication required (matches the rest of the Phase 2
API surface). Replace with per-user persistent storage when user accounts
land.
"""

from fastapi import APIRouter

from models.settings import AppSettings

router = APIRouter(tags=["settings"])

# Single process-lifetime settings instance
_current_settings = AppSettings()


@router.get("/settings", response_model=AppSettings)
async def get_settings() -> AppSettings:
    # Legacy "dim" preference is surfaced as the canonical "dark" theme.
    if _current_settings.theme == "dim":
        return _current_settings.model_copy(update={"theme": "dark"})
    return _current_settings


@router.put("/settings", response_model=AppSettings)
async def update_settings(payload: AppSettings) -> AppSettings:
    global _current_settings
    # Accept legacy "dim" writes but persist them as "dark" going forward.
    if payload.theme == "dim":
        payload = payload.model_copy(update={"theme": "dark"})
    _current_settings = payload
    return _current_settings
