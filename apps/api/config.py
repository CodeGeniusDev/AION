"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = "AION API"
    app_version: str = "0.1.0"
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "")
    model_calls_enabled: bool = os.getenv("AION_DISABLE_MODEL_CALLS", "0") != "1"
    log_level: str = os.getenv("AION_LOG_LEVEL", "INFO")
    # Bounded retention: max number of distinct task_ids whose Cognitive Bus
    # history and Immune reports are kept in memory at once. Oldest tasks
    # are evicted once this cap is exceeded (see
    # orchestration/workflow_runner.py::_track_task). Prevents the
    # previously-unbounded growth identified in the architecture audit.
    max_retained_tasks: int = int(os.getenv("AION_MAX_RETAINED_TASKS", "500"))
    # Rate limiting: requests allowed per client (by IP) per rolling window,
    # applied to POST /api/chat only (the only compute-heavy endpoint).
    rate_limit_requests: int = int(os.getenv("AION_RATE_LIMIT_REQUESTS", "60"))
    rate_limit_window_seconds: float = float(os.getenv("AION_RATE_LIMIT_WINDOW_SECONDS", "60"))
    # Authentication is OPT-IN via this flag. Defaulting to False preserves
    # the existing unauthenticated /api/chat contract that apps/web already
    # depends on (the frontend has no capability to send an API key, and
    # apps/web cannot be modified). Set AION_REQUIRE_AUTH=1 in a real
    # deployment once API keys have been provisioned via auth/store.py.
    require_auth: bool = os.getenv("AION_REQUIRE_AUTH", "0") == "1"
    default_tenant_id: str = os.getenv("AION_DEFAULT_TENANT_ID", "default")


settings = Settings()
