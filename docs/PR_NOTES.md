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
