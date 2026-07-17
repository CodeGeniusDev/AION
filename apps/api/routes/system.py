from fastapi import APIRouter

from models.system import HealthResponse, RootResponse

router = APIRouter(tags=["system"])


@router.get("/", response_model=RootResponse)
async def root() -> RootResponse:
    return RootResponse(message="AION API is running")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="healthy", service="AION API")

