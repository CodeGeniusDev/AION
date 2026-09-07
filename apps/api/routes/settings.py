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
    return _current_settings


@router.put("/settings", response_model=AppSettings)
async def update_settings(payload: AppSettings) -> AppSettings:
    global _current_settings
    _current_settings = payload
    return _current_settings
