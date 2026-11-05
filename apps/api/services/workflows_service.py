"""Workflow service: real, persisted workflow entities + genuine execution.

Workflows run through the existing WorkflowRunner in ``manual`` mode with
the workflow's own agent list — which is validated at creation time to
contain ONLY model-safe agents (planner / researcher / critic / memory, the
chat ``AgentId`` set). A workflow can therefore never reach desktop tools,
the bridge, or anything outside the in-process agent pipeline. The
``runs`` counter and ``state`` come from real execution, not demo data.
"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from memory.workflow_store import SQLiteWorkflowStore, WorkflowRecord
from models.chat import ChatRequest
from models.workflows import (
    Workflow,
    WorkflowCreateRequest,
    WorkflowRunResult,
    WorkflowsResponse,
)

# Canonical chat AgentIds — the ONLY agents a workflow may execute. This is
# the same set the Gemini function declarations expose (calculator/text/
# datetime tools aside); no desktop/bridge agent exists in this vocabulary.
MODEL_SAFE_AGENTS: set[str] = {"planner", "researcher", "critic", "memory"}

# Accepted display-name aliases at the API surface (case-insensitive).
_AGENT_ALIASES: dict[str, str] = {
    "planner": "planner",
    "research": "researcher",
    "researcher": "researcher",
    "critic": "critic",
    "memory": "memory",
}


def normalize_agents(display_agents: list[str]) -> list[str]:
    """Map display names to canonical AgentIds; reject anything model-unsafe.

    Raises HTTPException(400) so both POST /api/workflows and (defensively)
    run treat unknown agents as a hard error rather than silently widening
    the executable set.
    """
    agent_ids: list[str] = []
    for raw in display_agents:
        agent_id = _AGENT_ALIASES.get(raw.strip().lower())
        if agent_id is None or agent_id not in MODEL_SAFE_AGENTS:
            raise HTTPException(
                status_code=400,
                detail=f"Agent '{raw}' is not a model-safe agent. Allowed: Planner, Research, Critic, Memory.",
            )
        if agent_id not in agent_ids:
            agent_ids.append(agent_id)
    return agent_ids


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_workflows(store: SQLiteWorkflowStore) -> WorkflowsResponse:
    items = store.public_list()
    return WorkflowsResponse(items=items, total=len(items))


def get_workflow(store: SQLiteWorkflowStore, workflow_id: str) -> Workflow:
    found = store.public_get(workflow_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return found


def create_workflow(store: SQLiteWorkflowStore, payload: WorkflowCreateRequest) -> Workflow:
    agent_ids = normalize_agents(payload.agents)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Workflow name must not be empty")
    record = WorkflowRecord(
        id=f"wf-{uuid4().hex[:8]}",
        name=name,
        description=payload.description.strip(),
        agents=[a.strip() for a in payload.agents if a.strip()],
        agent_ids=agent_ids,
        runs=0,
        state="Ready",
        created_at=_now(),
        updated_at=_now(),
    )
    stored = store.create(record)
    return stored.to_public()


async def run_workflow(
    store: SQLiteWorkflowStore, runner, workflow_id: str, user_input: str,
) -> tuple[Workflow, WorkflowRunResult]:
    """Execute a workflow via the WorkflowRunner (manual mode, model-safe
    agents only). Exactly one in-flight run per workflow: the store's
    atomic claim rejects concurrent runs with 409. ``runs`` counts real
    attempts, successful or not."""
    record = store.get(workflow_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    # Defensive re-validation: a row whose agent_ids somehow escaped the
    # creation-time whitelist must still never execute an unsafe set.
    if not record.agent_ids or any(a not in MODEL_SAFE_AGENTS for a in record.agent_ids):
        raise HTTPException(
            status_code=400,
            detail="Workflow contains agents outside the model-safe set; it cannot be run.",
        )

    claimed = store.claim_for_run(workflow_id)
    if claimed is None:
        raise HTTPException(
            status_code=409,
            detail="Workflow is already running; wait for the current run to finish.",
        )

    request = ChatRequest(
        message=user_input.strip(),
        mode="manual",
        selected_agents=list(record.agent_ids),  # type: ignore[arg-type]  (validated above)
    )
    try:
        response = await runner.run(request, tenant_id=None)
    except Exception as exc:  # runner blew up — record and release the claim
        store.finish_run(workflow_id, error=str(exc)[:300])
        final = store.get(workflow_id)
        assert final is not None
        # Phase 2B: notify SSE subscribers of workflow run state change.
        try:
            from realtime.publishers import publish_workflow_run_updated
            from config import settings as _settings
            publish_workflow_run_updated(_settings.default_tenant_id, workflow_id=workflow_id, status="failed")
        except Exception:
            pass
        return final.to_public(), WorkflowRunResult(
            task_id="",  status="failed",
            answer="The workflow run failed before producing a response.",
            confidence=0.0, processing_time_ms=0, error=str(exc)[:300],
        )

    error = response.error if response.status == "failed" else None
    finished = store.finish_run(workflow_id, last_task_id=response.task_id, error=error)
    assert finished is not None
    # Phase 2B: notify SSE subscribers of workflow run state change.
    try:
        from realtime.publishers import publish_workflow_run_updated
        from config import settings as _settings
        publish_workflow_run_updated(_settings.default_tenant_id, workflow_id=workflow_id, status=response.status)
    except Exception:
        pass
    return (
        finished.to_public(),
        WorkflowRunResult(
            task_id=response.task_id,
            status=response.status,
            answer=response.answer,
            confidence=response.confidence,
            processing_time_ms=response.processing_time_ms,
            error=response.error,
        ),
    )
