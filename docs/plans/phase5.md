# Phase 5 Plan — Scheduler integration (pending approvals at fire time)

## Goal
Real, persistent schedules that, **at fire time, create PENDING approvals
and never execute anything**. The scheduler is a creator — it holds the
same powers chat holds after Phase 2, no more.

## Findings from inspection
- `desktop/aion_desktop/scheduler.py` exists but is **wired to nothing**
  (no importer, no tests) and stores callables in memory — unpicklable,
  so it can never survive a restart. It stays as-is (legacy scaffolding).
- The correct home is the backend: `ApprovalService.request_execution()`
  already creates task + pending ledger row + alert + audit and provably
  never dispatches (that is the Phase 2 guarantee, tested). The scheduler
  calling it inherits "create-only" by construction.
- `memory/workflow_store.py` (Phase 1) is the proven SQLite pattern:
  interface + `CREATE TABLE IF NOT EXISTS` + `AION_*_DB_PATH` env +
  `get_default_*()/reset_*()` module singletons.
- `ApprovalStore.list(tenant_id, status=...)` lets the scheduler check
  whether its last fired approval is still pending (backpressure).

## Design
### New `apps/api/models/schedules.py`
`Schedule` (API-facing): id, name, tool, parameters, interval_seconds
(0 = one-shot), first_delay_seconds, status `active|paused|completed|
canceled`, next_run_at, last_run_at, last_approval_id, fire_count,
created_at, updated_at. `ScheduleCreateRequest` (name, tool, parameters,
interval_seconds>=0, delay_seconds>=0).

### New `apps/api/memory/schedule_store.py`
`ScheduleStoreInterface` + `SQLiteScheduleStore` mirroring
workflow_store: `AION_SCHEDULE_DB_PATH` (empty → `:memory:`), safe
schema, JSON parameters column, `get_due(now_iso)`, `record_fire(id,
approval_id, next_run_at|None)`, `set_status`. No seeds — schedules are
user-created only.

### New `apps/api/services/schedule_runner.py`
`ScheduleRunner(store, approval_service, now_fn=time.monotonic-ish,
tick_seconds=1.0)`:
- `tick(now)` — pure, clock-injected, the testable core. For each due
  `active` schedule: if `last_approval_id` still `pending_approval`,
  skip (backpressure, never queue duplicates); else call
  `request_execution(tool, parameters, tenant_id=default,
  actor_key_id="scheduler", title=f"Scheduled: {name}")`, record the
  fire (increment count, compute next_run or mark `completed` for
  one-shots). Any exception → audit-free log + schedule stays active;
  the runner never calls `approve_and_claim`/`dispatch`.
- `start()/stop()` — daemon thread calling `tick()`; started from
  `main.py` only when `AION_SCHEDULER_ENABLED=1` (default off → zero
  behavior change for existing deployments/tests).

### New `apps/api/routes/schedules.py` (prefix /api, same auth posture as
workflows routes — unauthenticated-compatible contract)
- `GET /api/schedules` / `GET /api/schedules/{id}`
- `POST /api/schedules` — 404 unknown tool (same `known_desktop_tools()`
  gate), 422 non-JSON parameters; creating a schedule for a protected
  tool is fine — execution still needs a human.
- `POST /api/schedules/{id}/pause` / `/resume`
- `DELETE /api/schedules/{id}` → status `canceled` (row kept for history)

### Config & wiring (shared files, Mahnoor)
- `config.py`: `schedule_db_path`, `scheduler_enabled`
- `.env.example`: both documented, defaults off/in-memory
- `main.py`: include router; conditional thread start

### Frontend (backward compatible, minimal)
- `types/index.ts`: `Schedule` + `SchedulesResponse`
- `services/api.ts`: getSchedules/createSchedule/pauseSchedule/
  resumeSchedule/deleteSchedule
- `desktop-view.tsx`: new "Schedules" SectionCard — list with status
  badge, next-run time, fire count, pause/resume/cancel buttons,
  loading/error/empty states (same pattern as other sections).

## Tests
`apps/api/tests/test_schedules.py` (fake clock, MockBridgeClient
injected — asserts `bridge.calls == []`):
1. due schedule fires → pending_approval row + task + fire_count 1,
   bridge never touched;
2. one-shot → completed after one fire;
3. recurring → next_run advanced by interval;
4. backpressure: previous approval still pending → skipped;
5. unknown tool at creation → 404; bad params → 422;
6. persistence: store reopens from the same db file and keeps rows
   (restart simulation);
7. fake clock: paused not fired, resume re-arms, cancel terminal;
8. injection attempt: parameters cannot contain approval-control keys
   reaching the ledger (sanitize path reused).

## Live E2E
Bridge + API with `AION_SCHEDULER_ENABLED=1` + file-backed schedule db;
create `file_write` schedule (interval 2s); wait → pending approval
appears in `/api/approvals` (status pending_approval, NOT executed);
approve via API → executes once; restart API mid-life → schedule row
survives (GET shows same id/fire_count), fires again after restart.

## Risks
- Background thread in tests → never started in tests (tick() called
  directly with fake clock); default `scheduler_enabled=0` keeps the
  existing 428-test suite untouched.
- Fire-time failure must not crash thread → try/except around each tick.
- `request_execution` raises ApprovalError for unknown tool at fire
  time (tool list changed since creation) → mark schedule failed via
  log, leave row active=false? Decision: record error on schedule
  (`last_error`), pause it — silent infinite failure loops are worse.

## Gate checklist
backend pytest, desktop pytest, tsc, lint, live E2E — raw outputs.
