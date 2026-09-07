from fastapi import APIRouter

from agents.registry import registry
from config import settings
from models.system import HealthComponent, HealthResponse, RootResponse
from routes.chat import workflow_runner

router = APIRouter(tags=["system"])


@router.get("/", response_model=RootResponse)
async def root() -> RootResponse:
    return RootResponse(message="AION API is running")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    # Gemini: is the service configured with a key and model calls enabled?
    gemini_configured = workflow_runner.model_service.is_configured()
    gemini = HealthComponent(
        status="ok" if gemini_configured else "degraded",
        detail=f"{workflow_runner.model_service.model} ({'configured' if gemini_configured else 'no API key'})",
    )

    # Memory: can we reach the SQLite store and get a count?
    try:
        record_count = workflow_runner.memory_store.count()
        memory = HealthComponent(status="ok", detail=f"{record_count} record(s)")
    except Exception as exc:
        memory = HealthComponent(status="error", detail=str(exc)[:120])

    # Agents: how many are registered?
    agent_count = len(registry.list_identities())
    agents = HealthComponent(
        status="ok" if agent_count > 0 else "degraded",
        detail=f"{agent_count} registered",
    )

    # Overall: unhealthy if any component is error, degraded if any is degraded
    components = [gemini, memory, agents]
    if any(c.status == "error" for c in components):
        overall = "unhealthy"
    elif any(c.status == "degraded" for c in components):
        overall = "degraded"
    else:
        overall = "healthy"

    return HealthResponse(
        status=overall,
        service="AION API",
        version=settings.app_version,
        model_name=workflow_runner.model_service.model,
        gemini=gemini,
        memory=memory,
        agents=agents,
    )

