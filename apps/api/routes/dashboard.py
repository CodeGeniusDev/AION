from fastapi import APIRouter

from models.dashboard import DashboardResponse
from routes.chat import workflow_runner
from services.dashboard_service import get_dashboard

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard() -> DashboardResponse:
    return get_dashboard(workflow_runner.memory_store)
