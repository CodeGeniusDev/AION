from fastapi import APIRouter

from models.agents import AgentsResponse
from services.agents_service import get_agents

router = APIRouter(tags=["agents"])


@router.get("/agents", response_model=AgentsResponse)
async def agents() -> AgentsResponse:
    return get_agents()
