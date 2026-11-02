# PR Notes — `abdullah` → `main`

Summary: Human-in-the-loop desktop tool approval system (two-gate: backend
approval ledger + one-time bridge grant), plus phased build-out (Phases 0–7)
of real workflows, chat-created approval requests, a Desktop tab, browser
tools, scheduler, voice, and social scaffolding. Gemini function
declarations remain limited to `calculator`, `text_analysis`,
`current_datetime`; every desktop/file/browser action stays behind the human
approval gate.

## Shared apps/api files touched, by phase
Mahnoor owns `apps/api`. This is the running list of shared-surface changes
so conflicts can be checked before merge.

### Pre-phase work (approval system, commits `fec4b9b..972bf63`)
- `apps/api/config.py` — new approval env vars (`AION_APPROVAL_DB_PATH`,
  `AION_APPROVAL_TTL_SECONDS`, `AION_AGENT_BRIDGE_URL`, `AION_AGENT_SECRET`,
  `AION_BRIDGE_TIMEOUT_SECONDS`, `AION_PROTECTED_DESKTOP_TOOLS`,
  `AION_APPROVAL_DISPATCH_ASYNC`)
- `apps/api/main.py` — register `desktop` + `approvals`/audit routers
- `apps/api/.env.example` — approval env placeholders
- `apps/api/models/tasks.py`, `apps/api/models/approval.py`,
  `apps/api/models/notifications.py` — task lifecycle + approval/audit schemas
- `apps/api/routes/desktop.py`, `apps/api/routes/approvals.py` (includes
  `GET /api/audit`), `apps/api/routes/tasks.py`
- `apps/api/services/approval_service.py`,
  `apps/api/services/desktop_bridge_client.py`
- `apps/api/memory/approval_store.py` (ledger + audit)
- `apps/api/tools/registry.py`, `apps/api/tools/local_tools.py` — desktop tool
  names isolated from model-exposed declarations

### Phase 0 — Cleanup
- No `apps/api` source changes (verified existing suites: 372 backend tests
  pass). Changes were in `MVP.sh`, `desktop/`, and docs only.

### Phase 1 — Real Workflow entity
- `apps/api/config.py` — new `workflow_db_path` setting
  (`AION_WORKFLOW_DB_PATH`)
- `apps/api/.env.example` — `AION_WORKFLOW_DB_PATH` placeholder
- `apps/api/models/workflows.py` — added `WorkflowCreateRequest`,
  `WorkflowRunRequest`, `WorkflowRunResult`, `WorkflowRunResponse`
  (backward compatible; existing `Workflow` shape unchanged)
- `apps/api/routes/workflows.py` — real endpoints: `GET /api/workflows`,
  `GET /api/workflows/{id}`, `POST /api/workflows`,
  `POST /api/workflows/{id}/run`
- `apps/api/services/workflows_service.py` — demo dict replaced with
  store-backed service + model-safe agent whitelist
- `apps/api/memory/workflow_store.py` — new SQLite store (schema,
  seed-once, atomic `claim_for_run`)
- `apps/api/tests/test_workflows.py` — 22 new tests
- Frontend only (no contract changes): `types/index.ts`, `services/api.ts`,
  `components/workflows/workflows-view.tsx`

### Phase 2 — Chat-driven approval requests
- `apps/api/services/chat_approval.py` — NEW: chat-side integration that can
  only call `request_execution` (create pending approvals). Deterministic
  clause-anchored heuristic + optional single LLM classification (no function
  declarations); parameters validated against a per-tool whitelist with a
  forbidden-key scrub (`token|grant|secret|hash|approval|approve`); fails
  closed on any ambiguity. Never touches the bridge or the approve path.
- `apps/api/models/chat.py` — additive `PendingApprovalInfo` model + optional
  `ChatResponse.pending_approval` (backward compatible; existing fields
  unchanged)
- `apps/api/routes/chat.py` — lazy-import hook after `workflow_runner.run`:
  prepends an "Approval required" notice and links to the queue
  (`/tasks`); hook failures degrade to a normal chat response
- `apps/api/tests/test_chat_approvals.py` — 32 new tests: detections /
  non-detections, injection attempts (self-approval wording, tool-call
  spoofing, forbidden keys), proof that the chat path makes zero privileged
  calls (`approve_and_claim`/`reject`/`dispatch`) and that Gemini
  declarations remain calculator/text_analysis/current_datetime only
- No changes to `config.py`, `.env.example`, or `main.py` this phase
- Frontend (contract-compatible): `types/index.ts` (+`PendingApprovalInfo`,
  optional `pending_approval`), `components/chat/aion-message.tsx`
  (amber "Approval pending" card linking to the queue)

### Phase 3 — Desktop tab
- `apps/api/services/desktop_bridge_client.py` — new `health()` GET probe;
  deliberately sends no secret header (bridge /health is auth-free)
- `apps/api/routes/desktop.py` — NEW endpoint `GET /api/desktop/health`
  (always 200; offline bridge = `reachable:false` data, never an HTTP error;
  response carries no URL/token/tool material — asserted in tests)
- `apps/api/models/approval.py` — additive `DesktopHealthResponse`
- `apps/api/tests/test_desktop_approvals.py` — +2 tests (reachable mapping,
  offline-is-data, secret-leak scan); MockBridgeClient gains `health()`
- No changes to `config.py`, `.env.example`, or `main.py` this phase
- Frontend: new `app/desktop/page.tsx` + `components/desktop/desktop-view.tsx`
  (approval queue, task history with real outputs, bridge health, audit
  trail; loading/error/empty states; responsive); `sidebar.tsx` entry;
  `approval-queue.tsx` optional `fallback` prop; `status-badge.tsx` gains
  approval statuses; `types/index.ts` +`DesktopHealth`; `services/api.ts`
  +`getApprovals`/`getAudit`/`getDesktopHealth`; Playwright smoke test for
  `/desktop` (5 smoke tests total); `.gitignore` + Playwright run artifacts

### Phase 4 — Browser tools (Playwright) behind approval
- `desktop/aion_desktop/browser.py` — rewritten against the real Playwright
  API (the previous `start()`/`navigate()`/`click()` could not run): one
  active page per execution so navigate→screenshot compose; new
  `BrowserPolicy` (http/https only — `file:`/`chrome:`/`javascript:`…
  refused; loopback admin ports 3000/3001/8000/8010/8080/8443 refused;
  allowlist pins hosts, denylist always wins; post-redirect re-check)
  + `browser_policy_from_config`
- `desktop/aion_desktop/bridge.py` — `browser_navigate` no longer honors a
  requester-supplied `headless` param (config-only); `browser_screenshot`
  no longer honors a requester-supplied `output_path` (always derived
  inside the workspace) and now actually navigates its `url` param; both
  validate against the policy before launching Chromium; policy +
  headless wired from config in `build_app`
- `desktop/aion_desktop/config.py` + `desktop/config.yaml` — additive
  `browser.blocked_ports` / `browser.allowlist` / `browser.denylist`
- `desktop/tests/test_browser_policy.py` (NEW, 26 cases) and
  `desktop/tests/test_browser_executors.py` (NEW — executor contract with
  mocked manager + real-Chromium integration tests, auto-skip if the
  browser build is missing). Desktop suite 9 → 42 tests.
- `apps/api/tests/test_bridge_security.py` + `desktop/tests/test_bridge_security.py`
  — signature-only fix (`**kwargs`) to the `_executor_for` monkeypatch
- No API route/model/env changes this phase; approval gate, protected-tool
  list and Gemini declarations untouched (428 backend tests prove it)
- Install report: `playwright 1.64.1` pip-installed into `.venv` and
  `python -m playwright install chromium` downloaded Chromium build 1248
  (104.1 MiB headless-shell + full build; cache now ~612 MB — the Node
  build 1243 could not be reused because Python playwright 1.64 pins 1248)
- `browser_click`/`browser_type` deliberately NOT exposed: they would need
  approval-gate registration + param-hash coverage + stateful sessions;
  documented as planned in docs/AION_MVP_PLAN.md

## Phase 5 — Scheduler integration (pending approvals at fire time)

Shipped. Scheduled desktop actions fire **only into the approval queue** —
the runner is the least-powerful actor: it calls the same create-only
`ApprovalService.request_execution` path chat uses and provably never
touches the bridge, builds no grant, and cannot approve.

- `apps/api/models/schedules.py` (NEW) — `Schedule` wire shape
  (tenant-scoped, `next_run_at` nullable once finalized), create-request
  with JSON-safe parameters and bounded interval/delay
- `apps/api/memory/schedule_store.py` (NEW) — SQLite store mirroring the
  Phase 1 workflow-store pattern; `CREATE TABLE IF NOT EXISTS` + safe
  additive `tenant_id` migration; rows survive restart when
  `AION_SCHEDULE_DB_PATH` points at a file
- `apps/api/services/schedule_runner.py` (NEW) — clock-injectable `tick()`
  (fake-clock tested), backpressure (one outstanding human decision per
  schedule), unknown-tool fires pause instead of spinning; daemon thread
  started only when `AION_SCHEDULER_ENABLED=1` — default behavior is
  byte-for-byte unchanged
- `apps/api/routes/schedules.py` (NEW) — CRUD + pause/resume/cancel under
  the existing `get_current_principal`/role pattern; resume re-arms one
  interval ahead (never bursts paused time); cross-tenant reads are 404
- Shared files touched (Mahnoor): `apps/api/config.py`
  (`schedule_db_path`, `scheduler_enabled`), `apps/api/main.py` (router
  include + `start_scheduler_if_enabled()`), `apps/api/.env.example`
  (both vars documented)
- `apps/api/tests/test_schedules.py` (NEW, 11 tests) — fire creates
  pending + bridge call count is zero, one-shot completion, recurring
  reschedule, backpressure, tool-vanished pause, pause/resume, restart
  persistence, tenant isolation, route contract + lifecycle. Backend
  suite 428 → 439 tests.
- Frontend: `types/index.ts` (Schedule types), `services/api.ts` (5
  functions), `components/desktop/schedules-panel.tsx` (NEW — list,
  create form, pause/resume/cancel, loading/error/empty states),
  `desktop-view.tsx` mount + fixed the bridge hint text (`cli run`, not
  `cli serve`), `status-badge.tsx` schedule statuses
- Live E2E (raw output in the phase report): schedule → 1 s tick → pending
  approval (params content-redacted) → nothing executed → human approve →
  file written once → audit `requested(actor=scheduler, params_hash) →
  approved → claimed → granted → executed`; wrong-path attempt correctly
  refused by the workspace guard; backend restart preserved both rows
- Gemini declarations and protected-tool policy untouched and still
  test-proven; approval gate not weakened in any way
