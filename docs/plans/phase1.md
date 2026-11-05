# Phase 1 Plan — Real Workflow entity

## Goal
Replace demo workflow data with a real SQLite-backed Workflow entity and
make workflows genuinely runnable through the existing WorkflowRunner.

## Schema / Store (`apps/api/memory/workflow_store.py`)
- Interface `WorkflowStoreInterface` (ABC) + `SQLiteWorkflowStore`, mirroring
  `memory/task_store.py` patterns (per-call connection, `_init_schema` with
  `CREATE TABLE IF NOT EXISTS`, `get_default_workflow_store()` /
  `reset_workflow_store()` module singleton).
- Table `workflows`: `id TEXT PK, name TEXT, description TEXT,
  agents_json TEXT (display names, API shape), agent_ids_json TEXT
  (canonical model-safe AgentIds), runs INTEGER DEFAULT 0, state TEXT
  ('Ready'|'Running'), last_task_id TEXT, last_error TEXT,
  created_at TEXT, updated_at TEXT`.
- New env var `AION_WORKFLOW_DB_PATH` (empty = `:memory:`) in `config.py` +
  `.env.example`.
- Seed the 3 demo workflows **once** (only when the table is empty) as real
  rows with `runs=0` — demo counters were fake; counters start real.

## Agent safety ("model-safe agents only")
- Canonical mapping: `planner|researcher|critic|memory` (chat `AgentId`).
- Display aliases accepted on create: Planner, Research/Researcher, Critic,
  Memory. Anything else → 400. Runs use `mode="manual"` +
  `selected_agents=agent_ids` via `workflow_runner.run` — the workflow path
  can never reach desktop tools or Gemini function declarations
  (registry isolation already tested).

## Endpoints (`apps/api/routes/workflows.py`)
- `GET /api/workflows` — unchanged response shape (backward compatible).
- `GET /api/workflows/{id}` — 404 unknown.
- `POST /api/workflows` — body `{name, description, agents[]}` → 201
  Workflow. id auto-generated `wf-xxxxxxxx` (slug fallback).
- `POST /api/workflows/{id}/run` — body `{input: str}` → runs synchronously
  through WorkflowRunner (manual mode), returns
  `{workflow: Workflow, run: {task_id, status, answer, confidence,
  processing_time_ms, error}}`. `runs` increments on every attempt;
  `state` = "Running" while an execution is in flight, "Ready" otherwise
  (guarded with try/finally; a crash mid-run is recorded as last_error and
  the row returns to Ready on next sweep — stale "Running" older than the
  Gemini timeout is treated as Ready).

## Frontend
- `types/index.ts`: add `WorkflowRunResult`, `WorkflowRunResponse`,
  `WorkflowCreatePayload` (WorkflowData unchanged).
- `services/api.ts`: `createWorkflow()`, `runWorkflow()` (long-timeout for run).
- `components/workflows/workflows-view.tsx`: enable **New Workflow** with an
  inline create form (name, description, agent checkboxes limited to the 4
  model-safe agents) and per-card **Run** (prompt input + result panel).
  Existing loading/error/empty states kept; no new deps.

## Tests (`apps/api/tests/test_workflows.py`)
- seed idempotency (second store on same file doesn't reseed), list shape
  unchanged, create → get → run (model calls disabled) increments runs and
  state returns Ready, invalid agent → 400, unknown id → 404, run persists
  last_task_id, backward-compat of GET response fields.

## Risks
- Synchronous run can be slow with a live Gemini key (documented; frontend
  uses the long chat timeout). Stale "Running" rows after a crash — covered
  by the staleness rule above.
