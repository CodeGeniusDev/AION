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
