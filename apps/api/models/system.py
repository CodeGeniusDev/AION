from typing import Literal

from pydantic import BaseModel


class RootResponse(BaseModel):
    message: str


class HealthComponent(BaseModel):
    status: Literal["ok", "degraded", "error"]
    detail: str


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    service: str
    version: str
    gemini: HealthComponent
    memory: HealthComponent
    agents: HealthComponent

