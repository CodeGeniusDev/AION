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
