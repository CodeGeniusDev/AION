"""FastAPI entry point for the AION backend."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from routes.chat import router as chat_router
from routes.dashboard import router as dashboard_router
from routes.system import router as system_router

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

app.include_router(system_router)
app.include_router(dashboard_router, prefix="/api")
app.include_router(chat_router, prefix="/api")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, __: Exception) -> JSONResponse:
    """Return a consistent response for unexpected server errors."""
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred"})

