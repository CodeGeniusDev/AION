# AION

**AION — Artificial Intelligence Operating Nervous System**

AION is a multi-agent backend where specialized agents (Planner, Researcher,
Critic, Memory) are dynamically selected per task via a capability-based
"Cognitive DNA" registry, coordinate through an in-process publish/subscribe
message bus, and have their output independently checked by a lexical
verification layer before anything is written to persistent memory.

## Tech stack

- **Frontend:** Next.js App Router, TypeScript, Tailwind CSS, Lucide React
- **Backend:** Python, FastAPI, Uvicorn, Pydantic, SQLite (stdlib `sqlite3`)
- **Testing:** ESLint, TypeScript, Pytest
- **Local orchestration:** Docker Compose

## Project structure

```text
AION/
├── apps/
│   ├── web/                  # Next.js frontend
│   │   ├── app/               # App Router pages (dashboard, chat, agents, tasks, memory, research, workflows, settings)
│   │   ├── components/        # UI components per page
│   │   ├── services/api.ts    # Backend API client
│   │   └── types/             # Shared TypeScript types
│   └── api/                  # FastAPI backend
│       ├── agents/            # Agent implementations + Cognitive DNA registry
│       ├── auth/               # API-key auth, hashing, tenant resolution (opt-in)
│       ├── cognitive_bus/      # Task-scoped publish/subscribe message bus
│       ├── database/           # Placeholder for a future Postgres/Supabase backend (unused — SQLite is the real backend)
│       ├── evaluation/         # Benchmark dataset + evaluator for comparing routing configurations
│       ├── immune/              # Claim extraction + lexical verification layer
│       ├── memory/              # SQLite-backed Cognitive Memory store (real, persistent)
│       ├── models/              # Pydantic request/response and internal schemas
│       ├── observability/       # Structured logging, request/correlation IDs, rate limiting
│       ├── orchestration/       # WorkflowRunner, Dynamic Brain Formation, Research Pipeline
│       ├── routes/              # API route modules
│       ├── services/            # Route-facing service layer (some real, some demo — see API routes table)
│       ├── tools/               # Tool registry/executor + built-in deterministic tools
│       ├── tests/               # Backend test suite (509 tests)
│       └── main.py              # FastAPI application entry point
├── research/                 # Architecture notes
├── docker-compose.yml
└── README.md
```

## Frontend setup

```bash
cd apps/web
npm install
npm run dev
```

Available at [http://localhost:3000](http://localhost:3000). Pages: Dashboard,
AI Chat, Tasks, Agents, Memory, Research, Workflows, Desktop, Settings.

```bash
npm run lint
npm run typecheck
npm run build
```

## Backend setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
cp apps/api/.env.example apps/api/.env   # fill in real values locally; never commit this file
cd apps/api
uvicorn main:app --reload --port 8000
```

Available at [http://localhost:8000](http://localhost:8000), docs at
[http://localhost:8000/docs](http://localhost:8000/docs).

```bash
cd apps/api
pytest
```

## Desktop agent bridge (optional)

The local agent (`desktop/`) exposes desktop/browser/file tools over a
localhost-only HTTP bridge. Single documented run command (also used in
`docs/DEPLOYMENT.md` and `MVP.sh`):

```bash
cd desktop
export AION_AGENT_SECRET='your-secure-secret'   # env only — no --secret CLI flag
python -m aion_desktop.bridge
```

The bridge binds to `127.0.0.1:8080` only and refuses to start with an
empty or `change-me-in-production` secret. **It runs as a host process
only — it is deliberately NOT a Docker Compose service**, because it
executes real file/browser/desktop actions on this machine and must never
be given host access from a containerized stack.

## Human-in-the-loop desktop tool approvals

No protected desktop tool (open app, screenshot, browser navigation, file
read/write/copy) runs without an explicit human approval, enforced by two
independent gates:

1. **Backend approval ledger** (`apps/api/memory/approval_store.py`) owns
   the lifecycle `pending_approval → running → completed/failed` (plus
   terminal `rejected`/`expired`). A `POST /api/desktop/execute` request
   only _creates_ a pending approval and a linked task — it never executes.
   Every state change is an atomic conditional SQL update (guarded by
   `rowcount`), so an approved action runs **exactly once**: a second
   approve returns `409`, and the executed parameters are the approved
   snapshot re-verified by SHA-256 (no approve/execute TOCTOU).
2. **Bridge one-time grant token** — before execution the backend
   registers a single-use grant (`approval_id` + tool + SHA-256 token hash
   - expiry) with the bridge via `POST /approvals/grant`. `/tools/execute`
     now requires **both** `X-Aion-Secret` and a matching `X-Aion-Approval`
     grant, which is consumed atomically _before_ the tool runs. A leaked
     shared secret alone can no longer drive the desktop, and a replayed
     request is refused (`403 already_consumed`).

The bridge shared secret (`AION_AGENT_SECRET`) stays server-side; it is
never accepted from or returned to the frontend. An append-only `audit_log`
records the full lifecycle with secrets/token material redacted. Pending
approvals surface as alerts and in the approval queue on the tasks page.
What this does and does not defend against is enumerated in
`docs/THREAT_MODEL.md`.

## API routes

| Method | Route                                    | Data source                                                                                                                                                    |
| ------ | ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET`  | `/` , `/health`                          | Static                                                                                                                                                         |
| `POST` | `/api/chat`                              | **Real** — full pipeline: Dynamic Brain Formation → Agents → Cognitive Bus → Immune verification → Cognitive Memory write-back                                 |
| `GET`  | `/api/agents`                            | **Real** — live Cognitive DNA Agent Registry                                                                                                                   |
| `GET`  | `/api/tasks`, `/api/tasks/{id}`          | **Real** — derived from episodic Cognitive Memory records (no dedicated Task entity exists; this is the closest real data)                                     |
| `GET`  | `/api/memory`                            | **Real** — live counts from the SQLite-backed Cognitive Memory store                                                                                           |
| `GET`  | `/api/research`                          | **Real** — Immune-verified semantic memory records tagged as research findings                                                                                 |
| `GET`  | `/api/dashboard`                         | **Real** — aggregated from the Agent Registry and Cognitive Memory store                                                                                       |
| `GET`  | `/api/workflows`                         | **Real** — SQLite-backed Workflow entity store (list/detail/create/run); `runs` is a real counter, `state` derives from real executions |
| `POST` | `/api/desktop/execute`                   | **Real** — requests a protected desktop action; creates a task + pending approval and never executes (`202`)                                                   |
| `GET`  | `/api/approvals`, `/api/approvals/{id}`  | **Real** — tenant-scoped approval ledger (sanitized parameters)                                                                                                |
| `POST` | `/api/approvals/{id}/approve`, `/reject` | **Real** — human decision: approve wins the atomic claim, registers a bridge grant, and dispatches once (`202`/`409`/`410`); reject is terminal (`200`)        |
| `GET`  | `/api/audit`                             | **Real** — read-only, append-only execution audit trail (secret-free)                                                                                          |

### Chat orchestration

`POST /api/chat` accepts four modes: `auto`, `quick`, `research`, `manual`.
For `auto` mode, required agent domains are inferred from the message via
deterministic phrase matching, then resolved against the live Agent
Registry by capability (Dynamic Brain Formation) — not a hardcoded
keyword-to-agent map. If no agent can be confidently selected for a
required domain, it falls back to a simpler keyword router rather than
failing the request.

Every response is authored by `AION`. `used_agents`, `confidence`,
`processing_time_ms`, and `revision_count` reflect what actually happened
during that request — nothing is invented. `development_mode: true` means
no live model call was made (see Gemini section below).

## Gemini (optional)

AION works fully without a Gemini API key — agents fall back to
deterministic template responses, and this is clearly reported via
`development_mode: true` in every `/api/chat` response. Setting
`GEMINI_API_KEY` in `apps/api/.env` enables real model calls; when unset,
`GeminiService.is_configured()` returns `False` and no live call is
attempted. AION never reports a live model response as having succeeded
when it did not.

## Environment variables

See `apps/api/.env.example` for the complete, current list — copy it to
`apps/api/.env` and fill in real values locally. It documents every
variable actually read by `config.py`, including authentication, rate
limiting, task retention, and logging settings added during later
hardening passes. Never commit a real `.env` file.

## Run with Docker Compose

```bash
./scripts/preflight.sh      # PASS/WARN/FAIL: secret, DB paths, ports, .venv, chromium
docker compose up --build
curl -f http://localhost:8000/health   # api (also the container healthcheck)
curl -f http://localhost:3000/         # web
```

`docker-compose.yml` runs **api + web only** (the desktop bridge is a host
process, see above). It loads `apps/api/.env` (a real, git-ignored file you
create locally) — never `.env.example`, which intentionally contains no
real values. Both services have healthchecks and `restart: unless-stopped`;
the `aion_data` volume holds `aion_memory.db` and `aion_approvals.db` under
`/data` (`docker compose down -v` would wipe approval history — never on a
real deployment). Full details: `docs/DEPLOYMENT.md` §4.

## Known limitations

- **SQLite is the only implemented persistence backend.** `database/` and
  `memory/pgvector.py` are explicit, documented placeholders for a future
  Postgres/pgvector backend — not active in any configuration.
- **Single-process only.** The Cognitive Bus, Agent Registry, and rate
  limiter are in-memory and do not coordinate across multiple server
  instances.
- **Tenant isolation covers Cognitive Memory only** (the one subsystem with
  real cross-request query risk); the Cognitive Bus and Tool/Research
  layers remain task-scoped, not tenant-scoped.
- **Authentication is opt-in** (`AION_REQUIRE_AUTH=0` by default) so the
  existing frontend, which does not send an API key, keeps working
  unmodified.
