# UI Overhaul — Phase 2 plan (Real-time layer + truthful live status)

Branch: `abdullah` (PR #1 still open). Continuation of Phase 1. Same hard
rules: approval gate + threat model + Gemini declarations untouched and
their tests stay green, no demo/fake data, no new external DB, no new
dependencies, additive backend changes, and every rendered control real.

## Files to touch (grouped)

### 2A — Test isolation (do first)

- `apps/web/playwright.config.ts`: launch a real API subprocess and a real
  Next dev server on non-default ports with every `AION_*_DB_PATH` pointed
  at a per-run temp dir. `reuseExistingServer: false` and the
  `PLAYWRIGHT_PORT` env-var convention already in place from Phase 1 stay.
- `apps/api/main.py`: mount the test fixture router only when
  `AION_TEST_MODE=1`.
- `apps/api/routes/test_fixture.py` (NEW): `POST /api/_test/seed` and
  `POST /api/_test/reset` writing to the SAME stores the real endpoints
  read. Guarded so both return 404 when `AION_TEST_MODE` is not set.
- `apps/api/tests/test_test_fixture_phase2a.py` (NEW): proves 404 when off,
  200 + real writes when on.
- `apps/web/e2e/*.spec.ts`: replace every `test.skip(condition, …)` with a
  deterministic `beforeEach` that seeds via `/api/_test/seed`.
- `scripts/purge-test-data.md` (NEW): instructions for the developer to
  safely clean the currently-polluted live SQLite files without any agent
  touching them.

### 2B — SSE Event Hub (backend)

- `apps/api/realtime/__init__.py` (NEW)
- `apps/api/realtime/hub.py` (NEW): tenant-aware subscriber registry,
  bounded ring buffer for Last-Event-ID resume, per-client asyncio queue
  with drop-oldest backpressure + `resync` event, connection cap, publish
  helper that swallows its own errors.
- `apps/api/realtime/publishers.py` (NEW): thin wrappers for each event
  type so callers never build payloads inline.
- `apps/api/routes/stream.py` (NEW): `GET /api/stream` (text/event-stream),
  auth via `get_current_principal`, `Last-Event-ID` header honoured,
  15 s heartbeat, clean disconnect unsubscribe.
- Publishers wired at REAL code paths (never on a hot request path that
  must not fail):
  - `services/approval_service.py` — `approval.created`, `approval.updated`
    after every terminal transition (approved / rejected / running /
    completed / failed).
  - `memory/alert_store.py` — `alert.created`, `alert.updated`.
  - `memory/task_store.py` — `task.updated`.
  - `routes/conversation` path in `services/chat.py` — `conversation.updated`.
  - `services/schedule_runner.py` — `schedule.fired`.
  - `services/workflows_service.py` — `workflow.run.updated`.
  - `memory/consolidation.py` — `memory.written`.
  - `services/desktop_bridge_client.health()` + `/api/desktop/health` —
    `bridge.status` and `health.changed`.
- Hub must never propagate exceptions to publishers: wrap every publish
  call in `try/except`. Test explicitly proves approval succeeds when the
  hub raises.
- `apps/api/tests/test_realtime_hub_phase2b.py` (NEW): ordering, resume
  by Last-Event-ID, tenant isolation, drop-oldest under slow consumer,
  connection cap, redaction (approval params and bridge secret never in
  payloads), hub-failure isolation.

### 2C — Frontend real-time

- `apps/web/lib/realtime.ts` (NEW): typed `subscribe(name, handler)` +
  connection state machine (Live / Reconnecting / Offline) with
  exponential backoff, visibility pause, Last-Event-ID forwarding.
- `apps/web/components/layout/realtime-provider.tsx` (NEW): one provider
  mounted in `app/layout.tsx`; falls back to the existing polling if
  `/api/stream` returns 404 or EventSource is unavailable.
- `apps/web/components/layout/sidebar.tsx`: live connection indicator in
  the footer, real `readyState`-derived label.
- `apps/web/hooks/useNotifications.ts`: transport swap only — components
  unchanged. Subscribes to `alert.created` / `alert.updated` / `unread`
  deltas from the hub; keeps the existing 15 s poll as the fallback.
- Views listen and refetch on the relevant event:
  dashboard (health / task / agent / memory), tasks list + detail, alert
  view (approvals), desktop view (approvals + bridge), agents, workflows,
  memory counts. Small `data-flash` animation on updated rows, disabled
  under `prefers-reduced-motion`. Scroll and focus preserved.

### 2D — Truthful status

- `apps/api/services/dashboard_service.py::_evaluate_system_health`:
  add Desktop Bridge as an optional component ("not configured" when no
  `agent_secret`, "unavailable" when probe fails, "healthy" when it
  succeeds) with weight that DOES reduce the score when configured +
  offline. Report which components reduced the score.
- `apps/api/routes/approvals.py::approve_action`: bridge pre-flight
  before the atomic claim. Offline → 503 with `{ retry_hint: "start
  the bridge" }` and the row STAYS `pending_approval` (test proves the
  row is not claimed). Approve button on `/desktop` shows the reason.
- `apps/web/components/desktop/desktop-view.tsx`: single-source command
  constant (`DESKTOP_BRIDGE_START_CMD`); "Queue is clear" replaced by
  last-result state (green only when the last request completed
  successfully, amber/red otherwise).
- Agents: idle = neutral grey; red only for real error/offline. Show
  measured `successful/total` from `PerformanceHistory` separately from
  declared proficiency (labelled "declared"). Workload = additive
  `runs_last_24h` counter populated by the runners.
- Dashboard: real relative time + human title (no raw ISO or
  "Chat request: social_post" leak), summary cards link to their real
  destination, "confidence" hidden unless it's a measured value, remove
  the empty blue bar above "AION Online", let columns stretch to fill.
- Tasks: failed rows show the real failure reason from the store.

### 2E — Gates + live E2E

- Same five gates after every sub-step, all on the isolated Playwright
  stack (never the developer's real DBs).
- Live E2E added as `apps/web/e2e/realtime.spec.ts`:
  - Two browser contexts, create a task + approval in one → visible in
    the other within 2 s without reload.
  - Kill the bridge → health score drops and Approve is blocked with
    "bridge offline", approval row stays `pending_approval`. Restart →
    recovers live.
  - Kill SSE server connection → indicator shows Reconnecting; Last-Event-ID
    resume delivers events missed with no duplicates.

## Schema / endpoint changes (all additive)

- `GET /api/stream` — new SSE endpoint.
- `POST /api/_test/seed`, `POST /api/_test/reset` — new, only present when
  `AION_TEST_MODE=1`. Both return 404 otherwise.
- `DashboardResponse.system_health_detail.components[]` — Desktop Bridge
  entry may now appear with status `not_configured | healthy | unavailable`.
  Consumers must treat unknown statuses as informational.
- `ApprovalExecuteResponse` on `POST /api/approvals/{id}/approve` — 503
  added as a new error status when the bridge is offline before claiming.
  202/409/410 responses unchanged.
- `AgentActivity` (dashboard) gains additive `runs_last_24h: int` and
  `declared_proficiency: {label, value}` — existing fields unchanged.
- `RecentTask` additive `human_title: str` and `failure_reason: str|None`.

## Environment / configuration

- `AION_MEMORY_DB_PATH`, `AION_APPROVAL_DB_PATH`, `AION_PROFILE_DB_PATH`,
  `AION_WORKFLOW_DB_PATH`, `AION_SCHEDULE_DB_PATH` — every one must point
  at a per-run temp path in the Playwright stack.
- `AION_TEST_MODE=1` — enables `/api/_test/*`. Never set for normal dev.
- `AION_STREAM_MAX_CLIENTS` (default 100) and `AION_STREAM_RING_SIZE`
  (default 200) — documented in `.env.example`.
- Playwright uses `PLAYWRIGHT_API_PORT` (default 3124) + `PLAYWRIGHT_PORT`
  (already 3123 from Phase 1) so it never collides with the developer's
  :8000 + :3000 stack.

## Risks

- Behaviour change in `POST /approve` (503 when bridge offline) — the
  atomic claim is unchanged; only the pre-flight is new. Mitigated by an
  explicit test asserting the row stays `pending_approval` on 503.
- SSE under load can hold file descriptors / memory. Bounded by
  `AION_STREAM_MAX_CLIENTS`, per-queue drop-oldest, ring buffer capped at
  `AION_STREAM_RING_SIZE`. Documented defaults conservative for MVP.
- Publishers must never fail a business operation. Every `publish()` call
  site wraps in try/except and logs at debug only.
- Realtime provider fallback: if EventSource is unavailable (e.g. proxy
  stripping `text/event-stream`), the current poll stays in place so no
  UX regression.

## Stop conditions I'll obey

- Any gate red after two honest attempts → stop and ask.
- Any change that would weaken the approval gate, alter Gemini
  declarations, or require a new dependency beyond the 2 @radix-ui
  allowance → stop and ask.
- Any backend change that alters behavior for existing tests (beyond the
  documented additive 503 pre-flight) → stop and ask.
