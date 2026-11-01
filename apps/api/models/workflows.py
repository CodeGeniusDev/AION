from typing import Literal

from pydantic import BaseModel, Field

WorkflowState = Literal["Ready", "Running"]


class Workflow(BaseModel):
    id: str
    name: str
    description: str
    agents: list[str]
    runs: int = Field(ge=0)
    state: WorkflowState


class WorkflowsResponse(BaseModel):
    items: list[Workflow]
    total: int


class WorkflowCreateRequest(BaseModel):
    """POST /api/workflows body. `agents` are display names which the
    service maps to canonical model-safe AgentIds (planner/researcher/
    critic/memory); anything else is rejected."""

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    agents: list[str] = Field(min_length=1, max_length=8)


class WorkflowRunRequest(BaseModel):
    """POST /api/workflows/{id}/run body."""

    input: str = Field(min_length=1, max_length=4000)


class WorkflowRunResult(BaseModel):
    task_id: str
    status: str
    answer: str
    confidence: float
    processing_time_ms: int
    error: str | None = None


class WorkflowRunResponse(BaseModel):
    workflow: Workflow
    run: WorkflowRunResult
