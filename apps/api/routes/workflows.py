"""Workflow endpoints — real, persisted workflow entities.

GET /api/workflows keeps the exact historical response shape (id, name,
description, agents[], runs, state) so the frontend contract is unchanged;
the data is now genuine SQLite rows with real run counters and state
derived from actual execution. POST creates workflows (model-safe agents
only) and POST /{id}/run executes them through the existing WorkflowRunner
in manual mode.
"""

from fastapi import APIRouter, HTTPException

from memory.workflow_store import get_default_workflow_store
from models.workflows import (
    Workflow,
    WorkflowCreateRequest,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowsResponse,
)
from services.workflows_service import (
    create_workflow,
    get_workflow,
    get_workflows,
    run_workflow,
)

router = APIRouter(tags=["workflows"])


@router.get("/workflows", response_model=WorkflowsResponse)
async def workflows() -> WorkflowsResponse:
    return get_workflows(get_default_workflow_store())


@router.get("/workflows/{workflow_id}", response_model=Workflow)
async def workflow(workflow_id: str) -> Workflow:
    return get_workflow(get_default_workflow_store(), workflow_id)


@router.post("/workflows", response_model=Workflow, status_code=201)
async def create_workflow_route(payload: WorkflowCreateRequest) -> Workflow:
    try:
        return create_workflow(get_default_workflow_store(), payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {exc}") from exc


@router.post("/workflows/{workflow_id}/run", response_model=WorkflowRunResponse)
async def run_workflow_route(workflow_id: str, payload: WorkflowRunRequest) -> WorkflowRunResponse:
    # Lazy import mirrors routes/tasks.py: the shared runner singleton lives
    # with the chat route, and importing it here avoids an import cycle.
    from routes.chat import workflow_runner

    store = get_default_workflow_store()
    record, run = await run_workflow(store, workflow_runner, workflow_id, payload.input)
    return WorkflowRunResponse(workflow=record, run=run)
