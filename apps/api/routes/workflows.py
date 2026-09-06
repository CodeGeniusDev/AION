from fastapi import APIRouter

from models.workflows import WorkflowsResponse
from services.workflows_service import get_workflows

router = APIRouter(tags=["workflows"])


@router.get("/workflows", response_model=WorkflowsResponse)
async def workflows() -> WorkflowsResponse:
    # Deliberately left as demo data: no backend "Workflow" entity exists
    # anywhere in this codebase (no reusable workflow templates, no
    # persisted workflow-execution store). Dynamic Brain Formation
    # (orchestration/brain_former.py) forms an ephemeral per-task Brain,
    # which is conceptually adjacent but is not a reusable, named workflow
    # the way the frontend's WorkflowData model expects. Faking that
    # mapping would misrepresent what is actually implemented — see the
    # stabilization pass report for this explicit gap.
    return get_workflows()
