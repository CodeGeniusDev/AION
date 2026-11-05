from fastapi import APIRouter, HTTPException

from config import settings
from models.tasks import Task, TasksResponse
from routes.chat import workflow_runner
from services.task_service import (
    create_task,
    get_task,
    get_tasks,
    update_task_status,
    update_task_output,
)

router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=TasksResponse)
async def tasks() -> TasksResponse:
    # Real, persistent task store (SQLite-backed via memory.task_store).
    # Backward compatibility: pass the workflow runner's memory store
    # so task_service can fall back to episodic memory when empty.
    from memory.task_store import get_default_task_store
    return get_tasks(get_default_task_store(), workflow_runner.memory_store)


@router.get("/tasks/{task_id}", response_model=Task)
async def task(task_id: str) -> Task:
    found = get_task(task_id, workflow_runner.memory_store)
    if found is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return found


@router.post("/tasks", response_model=Task)
async def create_task_route(payload: dict) -> Task:
    """Create a new task (e.g. from a browser action or scheduled post).

    Expected payload: { "title": str, "agent": str, "status": str }
    """
    title = str(payload.get("title", ""))
    if not title:
        raise HTTPException(status_code=400, detail="Missing 'title'")
    agent = str(payload.get("agent", "aion"))
    status = str(payload.get("status", "pending"))
    valid_statuses = {"pending", "pending_approval", "running", "completed", "failed"}
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status '{status}'")
    return create_task(title, agent=agent, status=status)


@router.post("/tasks/{task_id}/status", response_model=Task)
async def update_task_status_route(task_id: str, payload: dict) -> Task:
    status = str(payload.get("status"))
    valid_statuses = {"pending", "pending_approval", "running", "completed", "failed", "approved"}
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status '{status}'")
    found = update_task_status(task_id, status)
    if found is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return found


@router.post("/tasks/{task_id}/output", response_model=Task)
async def update_task_output_route(task_id: str, payload: dict) -> Task:
    """Attach a tool output to a task (e.g. browser action result)."""
    from models.tool import ToolOutput
    output = ToolOutput(**payload)
    found = update_task_output(task_id, output)
    if found is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return found
