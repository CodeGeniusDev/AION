from fastapi import APIRouter

from models.chat import ChatRequest, ChatResponse
from orchestration.workflow_runner import WorkflowRunner

router = APIRouter(tags=["chat"])
workflow_runner = WorkflowRunner()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    return await workflow_runner.run(payload)
