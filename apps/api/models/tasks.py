from typing import Literal

from pydantic import BaseModel, Field

from models.tool import ToolOutput

TaskStatus = Literal["pending", "pending_approval", "running", "completed", "failed"]


class Task(BaseModel):
    id: str
    title: str
    agent: str
    status: TaskStatus
    confidence: int = Field(ge=0, le=100)
    created: str
    output: ToolOutput | None = None
    updated: str | None = None


class TasksResponse(BaseModel):
    items: list[Task]
    total: int
