"""User-facing workspace settings model.

Process-lifetime in-memory store — survives for the app's uptime but not
across restarts (Phase 2 scope). Replace with a persistent store when user
accounts (Phase 3+) require per-user settings.
"""

from typing import Literal

from pydantic import BaseModel


class AppSettings(BaseModel):
    workspace_name: str = "AION Workspace"
    default_view: str = "dashboard"
    preferred_model: str = "gemini-3.6-flash"
    theme: Literal["light", "system", "dim"] = "light"
    memory_enabled: bool = True
    verification_enabled: bool = True
    notify_task_completions: bool = True
    notify_system_health: bool = True
    notify_weekly_summary: bool = False
