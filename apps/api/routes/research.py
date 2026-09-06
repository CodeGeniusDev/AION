from fastapi import APIRouter

from models.research import ResearchResponse
from routes.chat import workflow_runner
from services.research_service import get_research

router = APIRouter(tags=["research"])


@router.get("/research", response_model=ResearchResponse)
async def research() -> ResearchResponse:
    return get_research(workflow_runner.memory_store)
