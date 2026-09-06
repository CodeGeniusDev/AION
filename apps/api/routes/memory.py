from fastapi import APIRouter

from models.memory import MemoryResponse
from routes.chat import workflow_runner  # the same live singleton /api/chat writes to
from services.memory_service import get_memory

router = APIRouter(tags=["memory"])


@router.get("/memory", response_model=MemoryResponse)
async def memory() -> MemoryResponse:
    return get_memory(workflow_runner.memory_store)
