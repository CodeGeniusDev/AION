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
│       ├── tests/               # Backend test suite (334 tests)
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
AI Chat, Tasks, Agents, Memory, Research, Workflows, Settings.

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

## API routes

| Method | Route | Data source |
| --- | --- | --- |
| `GET` | `/` , `/health` | Static |
| `POST` | `/api/chat` | **Real** — full pipeline: Dynamic Brain Formation → Agents → Cognitive Bus → Immune verification → Cognitive Memory write-back |
| `GET` | `/api/agents` | **Real** — live Cognitive DNA Agent Registry |
| `GET` | `/api/tasks`, `/api/tasks/{id}` | **Real** — derived from episodic Cognitive Memory records (no dedicated Task entity exists; this is the closest real data) |
| `GET` | `/api/memory` | **Real** — live counts from the SQLite-backed Cognitive Memory store |
| `GET` | `/api/research` | **Real** — Immune-verified semantic memory records tagged as research findings |
| `GET` | `/api/dashboard` | **Real** — aggregated from the Agent Registry and Cognitive Memory store |
| `GET` | `/api/workflows` | **Demo data.** No backend "Workflow" entity exists (no reusable workflow templates or execution store) — documented in `routes/workflows.py` rather than faked |

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
docker compose up --build
```

`docker-compose.yml` loads `apps/api/.env` (a real, git-ignored file you
create locally) — never `.env.example`, which intentionally contains no
real values.

## Known limitations

- **SQLite is the only implemented persistence backend.** `database/` and
  `memory/pgvector.py` are explicit, documented placeholders for a future
  Postgres/pgvector backend — not active in any configuration.
- **Single-process only.** The Cognitive Bus, Agent Registry, and rate
  limiter are in-memory and do not coordinate across multiple server
  instances.
- **`/api/workflows` is demo data** — no backend Workflow entity exists.
- **Tenant isolation covers Cognitive Memory only** (the one subsystem with
  real cross-request query risk); the Cognitive Bus and Tool/Research
  layers remain task-scoped, not tenant-scoped.
- **Authentication is opt-in** (`AION_REQUIRE_AUTH=0` by default) so the
  existing frontend, which does not send an API key, keeps working
  unmodified.
