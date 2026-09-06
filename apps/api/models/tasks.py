from typing import Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["completed", "running", "failed"]


class Task(BaseModel):
    id: str
    title: str
    agent: str
    status: TaskStatus
    confidence: int = Field(ge=0, le=100)
    created: str


class TasksResponse(BaseModel):
    items: list[Task]
    total: int
