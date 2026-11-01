# AION Architecture Reference

AION is a multi-agent AI operating nervous system. This reference covers the system architecture, tool system, cognitive bus, cognitive DNA, and the local agent automation layer — the working set a future session needs to extend or query the system.

## System Layers

| Layer | Technology | Key Files |
|---|---|---|
| Frontend | Next.js App Router, TypeScript, Tailwind, shadcn_ui | `apps/web/` |
| Backend | FastAPI + Uvicorn + Pydantic + SQLite | `apps/api/` |
| Multi-agent | Planner / Researcher / Critic / Memory | `apps/api/agents/` |
| Agent routing | Cognitive DNA registry + AgentRouter + DynamicBrainFormer | `apps/api/orchestration/` |
| Cognitive DNA | Domain enum, CapabilityTag, AgentIdentity, ModelDependency | `apps/api/models/cognitive_dna.py` |
| Message bus | CognitiveBus (in-process pub/sub, task-scoped) | `apps/api/cognitive_bus/` |
| Memory | SQLite-backed Cognitive Memory (real persistent store) | `apps/api/memory/` |
| Tool system | Tool registry + executor + built-in deterministic tools | `apps/api/tools/` |
| Chat pipeline | Dynamic Brain Formation → Agents → Cognitive Bus → Immune verification → Memory write-back | `apps/api/orchestration/` |
| Previous tasks | `services/tasks_service_old.py` (legacy, derived from episodic memory records) | `apps/api/services/` |

## Tool System

Tools are the primary extension point. Key files:

- `tools/base.py` — `BaseTool` interface
- `tools/registry.py` — `ToolRegistry` (process-wide global)
- `tools/builtin.py` — built-in deterministic tools
- `tools/executor.py` — `ToolExecutor` (timeout, error isolation, telemetry)
- `models/tool.py` — `ToolIdentity`, `ToolOutput`

Every tool MUST:
- Return a `ToolOutput` (never raise exceptions to the caller)
- Validate input before doing work
- Record performance via `ToolRegistry.record_run()`

## Domain Model

`Domain` enum (attached to each capability/tag):
`PLANNING`, `RESEARCH`, `REVIEW`, `MEMORY`, `GENERAL`, `COMPUTATION`,
`DESKTOP`, `WEB`, `FILE`, `SOCIAL`.

## Task Storage

Tasks are stored in a real SQLite-backed task store, not derived from episodic
memory. The task store pattern mirrors the memory store pattern. Key files:
- `memory/task_store.py` — `TaskStoreInterface`, `SQLiteTaskStore`
- `models/tasks.py` — `TaskStatus` (pending/running/completed/failed), `Task`
- `services/task_service.py` — business logic for task CRUD
- `routes/tasks.py` — FastAPI routes (`/api/tasks`, `/api/tasks/{id}`)

## Architecture Reference Files

- `apps/api/main.py` — FastAPI entry point, middleware, route registration
- `apps/api/orchestration/workflow_runner.py` — the core pipeline
- `apps/api/routes/chat.py` — `/api/chat` endpoint
- `apps/api/services/tasks_service_old.py` — legacy task derivation (do not use for new work)
