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
    # SQLite file path for Cognitive Memory persistence. Default is empty
    # (which means in-memory SQLite, lost on restart). Set to a real path
    # (e.g. "/data/aion_memory.db") for durability across process restarts.
    # Docker Compose mounts a volume at /data by default.
    memory_db_path: str = os.getenv("AION_MEMORY_DB_PATH", "")
    # --- Human-in-the-loop desktop tool approvals ---------------------
    # Approval ledger + audit log SQLite path. Empty keeps the ledger
    # in-memory (hermetic tests); deployments set a real file path.
    approval_db_path: str = os.getenv("AION_APPROVAL_DB_PATH", "")
    # How long a pending approval request stays approvable before it
    # expires (5 minutes by default — an expired request can never run).
    approval_ttl_seconds: int = int(os.getenv("AION_APPROVAL_TTL_SECONDS", "300"))
    # The desktop agent bridge. Shared secret for server-to-server calls
    # ONLY — env-derived, never returned to or accepted from the frontend.
    agent_bridge_url: str = os.getenv("AION_AGENT_BRIDGE_URL", "http://127.0.0.1:8080")
    agent_secret: str = os.getenv("AION_AGENT_SECRET", "")
    bridge_timeout_seconds: float = float(os.getenv("AION_BRIDGE_TIMEOUT_SECONDS", "30"))
    # Tools that always require an explicit human approval before the
    # bridge executes them. desktop_list_apps is exempt by default
    # (read-only process list); voice tools follow the same env-driven
    # policy. Comma-separated list.
    protected_desktop_tools: str = os.getenv(
        "AION_PROTECTED_DESKTOP_TOOLS",
        "desktop_open_app,desktop_screenshot,browser_navigate,"
        "browser_screenshot,file_read,file_write,file_copy",
    )
    # True (default): an approved action is dispatched to the bridge in a
    # BackgroundTask, so the approve request returns 202 immediately while
    # the desktop tool runs. False dispatches inline before the response —
    # used by tests that assert the terminal state in the same tick.
    approval_dispatch_async: bool = os.getenv("AION_APPROVAL_DISPATCH_ASYNC", "1") == "1"


settings = Settings()
