from fastapi import APIRouter, HTTPException

from models.tasks import Task, TasksResponse
from routes.chat import workflow_runner
from services.tasks_service import get_tasks

router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=TasksResponse)
async def tasks() -> TasksResponse:
    return get_tasks(workflow_runner.memory_store)


@router.get("/tasks/{task_id}", response_model=Task)
async def task(task_id: str) -> Task:
    found = workflow_runner.memory_store.get(task_id)
    if found is None or found.type != "episodic":
        raise HTTPException(status_code=404, detail="Task not found")
    from services.tasks_service import _parse_agent, _parse_status
    status = _parse_status(found.content)
    return Task(
        id=found.memory_id, title=found.content[:90], agent=_parse_agent(found.content),
        status=status, confidence=100 if status == "completed" else 0,
        created=found.created_at.isoformat(),
    )
