# PR #1 Reviewer Guide (abdullah → main) — for Mahnoor

Purpose of the branch: **human-in-the-loop desktop approvals + phased
desktop build-out** (Phases 0–7). No commits touch `main`; the branch is a
clean fast-forward over both `origin/main` and `origin/mahnoor` (both are
ancestors — verified 2026-11-02, zero merge conflicts).

Per-phase chronological log: `docs/PROGRESS.md`. Phase design docs:
`docs/plans/phase0..7.md`.

---

## 1. Shared apps/api files — what changed and why

| File | Change | Why |
|---|---|---|
| `config.py` | +10 settings (all with safe defaults, listed in §3) | approval ledger, bridge client, scheduler, workflow/schedule stores are all env-opt-in; defaults keep current behavior (in-memory DBs, scheduler off, auth off) |
| `main.py` | +14 lines: include 5 new routers (`approvals`, `desktop`, `workflows`, `schedules`, `voice`) and start the opt-in scheduler thread | pure additive wiring; no existing middleware/route order changed |
| `.env.example` | +24 lines: new env docs, no real values | onboarding template only |
| `models/tasks.py` | `TaskStatus` union extended with `"pending_approval"` | approvals create tasks that await a human; existing statuses unchanged |
| `models/chat.py` | `ChatResponse` gained optional `pending_approval: dict \| None` | additive; old clients ignore it (backward-compat guarantee §4) |
| `routes/chat.py` | after generating a reply, calls `chat_approval.handle_chat_desktop_request()` and attaches the pending-approval info to the response | the Phase 2 chat→approval link; create-only by construction |
| `routes/approvals.py` (NEW) | queue list/get/approve/reject + `/api/audit` | the human decision surface; role-gated (`WRITE_ROLES`) when auth is on |
| `routes/desktop.py` (NEW) | `POST /api/desktop/execute` (creates a pending approval — never executes directly) + `GET /api/desktop/health` | health degrades to `{"online": false}` instead of erroring |
| `routes/workflows.py` | demo data replaced by real store: GET list/detail, POST create, POST `{id}/run` | same response shape as the old demo payload; `runs` is now a real counter, `state` derives from real execution |
| `routes/schedules.py` (NEW) | schedule CRUD (list/get/create/pause/resume/delete) | auth + tenant scoped like approvals; creation only queues pending approvals |
| `routes/voice.py` (NEW) | `GET /api/voice/status`, `POST /api/voice/say` | availability-as-data; uninstalled optional deps are 200 JSON states, never crashes |
| `services/approval_service.py` (NEW) | ledger lifecycle: request → pending → (human) approve → claim → grant → execute; atomic transitions + append-only audit | the single enforcement point for "nothing runs without a human" |
| `services/desktop_bridge_client.py` (NEW) | HTTP client for the local bridge (shared secret header, one-time grant header) | server-to-server only; secret never accepted from or returned to the frontend |
| `services/chat_approval.py` (NEW) | heuristic + optional LLM classifier that can ONLY produce pending rows | classifier uses plain `generate()` — physically cannot invoke tools; parameter whitelist drops spoofed keys (`token|grant|secret|hash|approval|approve`) |
| `services/schedule_runner.py` (NEW) | clock-injectable tick loop; at fire time calls `request_execution` only; backpressure: one outstanding decision per schedule | scheduled actions never auto-execute |
| `services/workflows_service.py`, `memory/workflow_store.py`, `memory/schedule_store.py`, `memory/approval_store.py`, `memory/task_store.py` (NEW/extended) | SQLite-backed stores, `CREATE TABLE IF NOT EXISTS` on init, additive column migration for schedules (`tenant_id`) | in-memory default when no DB path is set, so tests and dev need no files |
| `tools/registry.py` + `tools/schema.py` + `tools/local_tools.py` | desktop tools registered in a SEPARATE namespace from model-exposed function declarations | **Gemini still sees exactly `calculator`, `text_analysis`, `current_datetime`** — enforced by `test_desktop_tools_isolation.py` and `test_chat_approvals.py` |

## 2. New endpoints (19)

All follow existing patterns: `response_model` + auth dependency +
rate limits; cross-tenant reads return 404.

- Approvals: `GET /api/approvals`, `GET /api/approvals/{id}`,
  `POST /api/approvals/{id}/approve` (202), `POST /api/approvals/{id}/reject`,
  `GET /api/audit`
- Desktop: `POST /api/desktop/execute` (202, creates pending approval),
  `GET /api/desktop/health`
- Workflows: `GET /api/workflows`, `GET /api/workflows/{id}`,
  `POST /api/workflows` (201), `POST /api/workflows/{id}/run`
- Schedules: `GET /api/schedules`, `GET /api/schedules/{id}`,
  `POST /api/schedules` (201), `POST /api/schedules/{id}/pause`,
  `POST /api/schedules/{id}/resume`, `DELETE /api/schedules/{id}`
- Voice: `GET /api/voice/status`, `POST /api/voice/say`
- Chat (existing endpoint): response gains `pending_approval` field

## 3. New environment variables (apps/api/.env.example has details)

| Var | Default | Notes |
|---|---|---|
| `AION_AGENT_BRIDGE_URL` | `http://127.0.0.1:8080` | local desktop bridge |
| `AION_AGENT_SECRET` | empty | REQUIRED to execute anything; the bridge refuses empty/placeholder secrets. Env-only, never logged |
| `AION_BRIDGE_TIMEOUT_SECONDS` | `30` | |
| `AION_PROTECTED_DESKTOP_TOOLS` | 8 tools incl. `social_post` | comma list; anything not protected/known is 404 everywhere |
| `AION_APPROVAL_DB_PATH` | empty = in-memory | SQLite ledger |
| `AION_APPROVAL_TTL_SECONDS` | `300` | expired requests can never run |
| `AION_APPROVAL_DISPATCH_ASYNC` | `1` | `0` dispatches inline (tests use this) |
| `AION_WORKFLOW_DB_PATH` | empty = in-memory | |
| `AION_SCHEDULE_DB_PATH` | empty = in-memory | |
| `AION_SCHEDULER_ENABLED` | `0` | daemon thread only when explicitly on |

Desktop-side (`desktop/.env.example`): `AION_AGENT_SECRET`, and Phase 7
placeholders `AION_SOCIAL_META_*`, `AION_SOCIAL_PINTEREST_*`,
`AION_SOCIAL_TIKTOK_*` (all empty → dry-run only).

## 4. Backward-compatibility guarantees

- No existing endpoint URL, method, or response field changed shape.
  Additions only (`pending_approval` in chat, `runs`/`state` semantics in
  workflows keep the old field set).
- The frontend consumes these additively (`types/index.ts`,
  `services/api.ts` follow existing call patterns); no new npm deps
  (Web Speech wrapper is hand-typed).
- `AION_REQUIRE_AUTH` opt-in semantics unchanged; with auth off, everything
  behaves as before on the `default` tenant.
- All new stores default to in-memory unless a DB path env is set — CI and
  test suites stay hermetic (`:memory:`).
- Gemini function declarations verified by tests to remain exactly
  `calculator, text_analysis, current_datetime`.

## 5. New SQLite tables (created idempotently on first use)

- `approval_requests`, `audit_log` (approval store)
- `tasks` (task store — status may be `pending_approval`)
- `workflows` (workflow store, seeds 3 demo rows once)
- `schedules` (schedule store; has an additive `ALTER TABLE` migration for
  `tenant_id` guarded by `PRAGMA table_info`)
- existing `memories` / `conversations` / `messages` / `alerts` untouched

## 6. Threat model — what reviewers must not let slip

- Chat, scheduler and LLM paths can **only create pending approvals**.
  Approving, executing, or seeing grant tokens is physically unreachable
  from them (spied/ExplodingBridge tests prove zero calls).
- Bridge enforces two gates: shared secret + one-time, tool-bound,
  expiring grant hash (SHA-256 only; raw tokens never stored).
- Config decides security-relevant modes (browser headlessness, voice
  backends, social live mode) — request parameters are ignored.
- OAuth tokens live only in `~/.aion` (0600, symlink/permission-refusing
  vault) and never enter git, logs, results, or the audit trail.

## 7. How to run the full suite

```bash
# Backend (456 tests)
cd apps/api && ../../.venv/bin/python -m pytest tests/ -q

# Desktop bridge (63 tests)
cd desktop && ../.venv/bin/python -m pytest tests/ -q

# Frontend gates
cd apps/web && npx tsc --noEmit && npm run lint

# Playwright smoke (needs dev server, see e2e/smoke.spec.ts)
cd apps/web && npx playwright test

# Preflight before any real run
bash scripts/preflight.sh
```

## 8. Known follow-ups (intentionally not in this PR)

- Live social posting is dark: needs owner developer apps/credentials +
  TikTok & `instagram_content_publish` app review (docs/PROGRESS.md).
- `business_schedule` tool, browser click/type, PyAutoGUI-grade input:
  planned, not built.
- Docker/compose updates: see docs/DEPLOYMENT.md (bridge stays a HOST
  process — never containerized with host access).

## 9. UI Overhaul Phase 1 — shared apps/api files (for Mahnoor)

All changes are ADDITIVE/backward compatible; the approval gate, threat
model and Gemini tool declarations (calculator, text_analysis,
current_datetime) were not touched and their tests stay green.

| File | Change | Why |
|---|---|---|
| `models/settings.py`, `routes/settings.py` | theme Literal extended with `"dark"`; legacy `"dim"` normalized to `"dark"` on read and write | single light/dark/system vocabulary across header, Settings and Profile |
| `memory/alert_store.py`, `models/notifications.py`, `routes/alerts.py` | additive `created_at` (ISO) and `link` fields on alerts (+ task-alert deep links) | bell popover needs relative time and real deep-links (`/tasks?open=ID`, `/desktop?approval=ID`) |
| `memory/profile_store.py` (NEW), `models/profile.py` (NEW), `routes/profile.py` (NEW) | SQLite profile + persisted settings store (`AION_PROFILE_DB_PATH`, default git-ignored `apps/api/.data/profile.db`), GET/PUT `/api/profile` | header/greeting/Profile read ONE real profile; settings survive restart; conftest forces a temp path so tests never touch the real file |
| `routes/search.py` (NEW), `models/search.py` (NEW), `main.py` | additive GET `/api/search?q=&limit=` — 8 grouped collectors over existing stores, ranking, tenant isolation; approval/schedule parameters NEVER returned | global search without new DBs or demo data |
| `security/redaction.py` (NEW), `routes/chat.py`, `models/chat.py` | credentials stripped at the chat request boundary BEFORE store/model/approval/alert paths; additive `ChatResponse.warnings: list[str]` | Secret Guard: raw values never reach conversation store, memory, logs, approval params or Gemini |
| `config.py`, `.env.example` | +`profile_db_path` setting, env documented | follows the existing AION_*_DB_PATH pattern |
| `services/dashboard_service.py`, `services/task_service.py`, `routes/events.py`, `cognitive_bus/bus.py`, `services/approval_service.py`, `services/startup_guard.py`, `models/dashboard.py`, `models/notifications.py` | 1A–1C support: real dashboard intelligence fields, event stream wiring, startup warning tweaks consumed by the new header/shell | additive fields only — response shapes of existing endpoints unchanged |
| `tests/conftest.py` + 8 new test modules | temp profile-DB env, agent-registry isolation snapshot, ~140 new tests (search, profile, alerts, redaction tables, shell endpoints) | test data lives only in temp/in-memory DBs |
