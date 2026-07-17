# AION

**AION — Artificial Intelligence Operating Nervous System**

AION is an Artificial Intelligence Operating Nervous System where specialized AI agents collaborate, share context and work together as one intelligent system.

## Tech stack

- **Frontend:** Next.js App Router, TypeScript, Tailwind CSS, shadcn/ui foundation, and Lucide React
- **Backend:** Python, FastAPI, Uvicorn, Pydantic, and python-dotenv
- **Testing:** ESLint, TypeScript, and Pytest
- **Local orchestration:** Docker Compose

## Project structure

```text
AION/
├── apps/
│   ├── web/                  # Next.js frontend foundation
│   │   ├── app/              # App Router pages
│   │   ├── components/       # Shared layout and UI components
│   │   ├── hooks/            # Future frontend hooks
│   │   ├── services/         # Future frontend API clients
│   │   ├── types/            # Shared TypeScript types
│   │   └── utils/            # Frontend utilities
│   └── api/                  # FastAPI backend
│       ├── agents/           # Agent placeholders
│       ├── cognitive_bus/    # Cognitive message schema and bus placeholder
│       ├── database/         # Supabase placeholder
│       ├── memory/           # pgvector placeholder
│       ├── models/           # Pydantic request and response models
│       ├── orchestration/    # Routing, workflow execution, and synthesis
│       ├── routes/           # API route modules
│       ├── services/         # Service layer and integration placeholders
│       ├── tests/            # Backend tests
│       └── main.py           # FastAPI application
├── research/                 # Architecture research and notes
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

## Frontend setup

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

The frontend is available at [http://localhost:3000](http://localhost:3000). The root route redirects to `/dashboard`. The responsive application includes Dashboard, AI Chat, Tasks, Agents, Workflows, Memory, Research, and Settings pages.

Useful frontend checks:

```bash
npm run lint
npm run typecheck
npm run build
```

## Backend setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
cp apps/api/.env.example apps/api/.env
cd apps/api
uvicorn main:app --reload --port 8000
```

The API is available at [http://localhost:8000](http://localhost:8000), with interactive documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

Run backend tests from `apps/api` while the virtual environment is active:

```bash
pytest
```

## API routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/` | API availability message |
| `GET` | `/health` | Service health status |
| `GET` | `/api/dashboard` | Demo dashboard metrics, tasks, and agent activity |
| `POST` | `/api/chat` | AION routing and unified multi-agent response |

### Chat orchestration

The chat API accepts four modes: `auto`, `quick`, `research`, and `manual`. Every successful response is authored by `AION`; specialist output is combined into one answer, while the UI receives only safe process summaries.

```json
{
  "message": "Research the future of solar energy in Pakistan",
  "mode": "auto",
  "selected_agents": [],
  "conversation_id": "optional-id",
  "memory_enabled": true,
  "verification_enabled": true
}
```

The response includes `used_agents`, deterministic `confidence`, complete `processing_time_ms`, `selection_summary`, sources, and a safe error field. When Gemini is unavailable, AION returns a clearly marked development-mode response without crashing.

Initial routing rules:

- Plans, roadmaps, steps, and strategy use Planner.
- Research, comparisons, and analysis use Planner, Researcher, and Critic.
- Reviews and verification use Critic.
- Previous or saved context requests include Memory.
- Simple requests use a direct AION response.

Confidence starts at `0.50`, adds agent completion, critic approval, verification, and source signals, then subtracts model-fallback and agent-error penalties. It is never random.

## Run with Docker Compose

```bash
docker compose up --build
```

## Environment variables

The checked-in `.env.example` files contain safe placeholders only. Copy them to local `.env` files and never commit actual credentials.

```env
GEMINI_API_KEY=
DATABASE_URL=
NEXT_PUBLIC_API_URL=http://localhost:8000
AION_DISABLE_MODEL_CALLS=0
```

## Current development status

**Phase 3 — AION orchestration.** Chat now defaults to AION Auto, routes tasks to the smallest useful agent set, runs a controlled workflow through the Cognitive Bus, and returns one final AION response with safe process summaries, confidence, and timing. The interface also supports Quick Answer, Research Team, and Manual Agents modes. Live sources, durable memory, LangGraph, Supabase PostgreSQL, pgvector persistence, streaming progress, and cancellation remain future work.
