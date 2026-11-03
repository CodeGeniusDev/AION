"""FastAPI entry point for the AION backend."""

from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from observability.context import bind_request_context, reset_request_context
from observability.logging_config import configure_logging, get_logger
from routes.agents import router as agents_router
from routes.approvals import router as approvals_router
from routes.schedules import router as schedules_router
from routes.voice import router as voice_router
from routes.test_fixture import router as test_fixture_router
from routes.chat import router as chat_router
from routes.alerts import router as alerts_router
from routes.dashboard import router as dashboard_router
from routes.desktop import router as desktop_router
from routes.events import router as events_router
from routes.feedback import router as feedback_router
from routes.memory import router as memory_router
from routes.research import router as research_router
from routes.search import router as search_router
from routes.settings import router as settings_router
from routes.profile import router as profile_router
from routes.system import router as system_router
from routes.tasks import router as tasks_router
from routes.workflows import router as workflows_router

configure_logging(settings.log_level)
logger = get_logger("main")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Foundation API for the AION multi-agent system.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Bind a request_id/correlation_id to every request for structured
    logging and end-to-end tracing, and surface the request_id in a
    response header so a caller can correlate their own logs with AION's.
    Does NOT alter any endpoint's JSON response body/contract — only adds
    response headers and server-side log lines.
    """
    incoming_correlation_id = request.headers.get("x-correlation-id")
    request_id, correlation_id = bind_request_context(correlation_id=incoming_correlation_id)
    started = perf_counter()
    logger.info("request_started method=%s path=%s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed method=%s path=%s", request.method, request.url.path)
        raise
    latency_ms = round((perf_counter() - started) * 1000, 2)
    logger.info(
        "request_completed method=%s path=%s status=%s latency_ms=%s",
        request.method, request.url.path, response.status_code, latency_ms,
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Correlation-ID"] = correlation_id
    reset_request_context()
    return response


app.include_router(system_router)
app.include_router(dashboard_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(feedback_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(profile_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(workflows_router, prefix="/api")
app.include_router(research_router, prefix="/api")
app.include_router(alerts_router, prefix="/api")
app.include_router(desktop_router, prefix="/api")
app.include_router(approvals_router, prefix="/api")
app.include_router(schedules_router, prefix="/api")
app.include_router(voice_router, prefix="/api")
# Phase 2A: /api/_test/* fixture endpoints. Handlers self-guard with
# AION_TEST_MODE and return 404 when the flag is off, so the router is
# always safe to include — production traffic can never distinguish it
# from any unknown path.
app.include_router(test_fixture_router, prefix="/api")

# Phase 5 scheduler: no-op unless AION_SCHEDULER_ENABLED=1. Fires create
# PENDING approvals only — execution still requires a human decision.
from services.schedule_runner import start_scheduler_if_enabled  # noqa: E402

start_scheduler_if_enabled()

# Phase B startup safety: logs a WARNING when AION_REQUIRE_AUTH is off and
# the desktop bridge is reachable. Log-only — never blocks or changes
# request handling.
from services.startup_guard import check_startup_safety  # noqa: E402

check_startup_safety()


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Return a consistent response for unexpected server errors, and log
    the real exception server-side without leaking it to the caller."""
    logger.exception("unhandled_exception error=%s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred"})
