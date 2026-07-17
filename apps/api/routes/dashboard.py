from fastapi import APIRouter

from models.dashboard import DashboardResponse
from services.dashboard_service import get_dashboard_data

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard() -> DashboardResponse:
    return get_dashboard_data()

