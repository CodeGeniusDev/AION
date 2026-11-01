# AION — Deployment & Local Agent Setup

## 1. Prerequisites

| Tool                   | Purpose                | Required                |
| ---------------------- | ---------------------- | ----------------------- |
| Python 3.11+           | Backend + local agent  | ✅                      |
| Node.js 18+ + npm      | Frontend               | ✅ (optional for MVP-1) |
| Playwright             | Browser control        | ✅ (MVP-2)              |
| PyAutoGUI              | Desktop control        | ✅ (MVP-2)              |
| openai-whisper or Vosk | Voice STT              | ✅ (MVP-4)              |
| Edge TTS or pyttsx3    | Voice TTS              | ✅ (MVP-4)              |
| aiohttp / httpx        | HTTP for local bridges | ✅                      |
| pytest                 | Testing                | ✅ (already present)    |

## 2. Step-by-step setup

### 2.1. Start the backend

```bash
cd <path-to-your-AION-checkout>   # e.g. the root of this repository
source .venv/bin/activate
cp apps/api/.env.example apps/api/.env   # fill GEMINI_API_KEY if desired
cd apps/api
uvicorn main:app --reload --port 8000
```

### 2.2. Start the frontend

```bash
cd <path-to-your-AION-checkout>/apps/web
npm install
npm run dev
```

Open http://localhost:3000 — you land on Dashboard (auto-redirect to `/dashboard`).

### 2.3. Start the local agent

The single documented run command (also used in MVP.sh and README):

```bash
cd desktop
export AION_AGENT_SECRET='your-secure-secret'   # env only — no --secret CLI flag
python -m aion_desktop.bridge
```

The local agent starts a local HTTP bridge on `http://127.0.0.1:8080` (localhost only) that AION calls to execute tools. The bridge refuses to start with an empty or `change-me-in-production` secret.

### 2.4. Wire AION ↔ local agent

- The backend reaches the bridge only through the approval ledger: a
  protected tool is requested via `POST /api/desktop/execute` (creates a
  pending approval), a human approves via `POST /api/approvals/{id}/approve`,
  and the backend registers a one-time grant with the bridge before it
  dispatches `POST /tools/execute`. The bridge returns
  `{ success: bool, result: any, task_id: str, error?: str }`.
- `AION_AGENT_SECRET` is read from the backend environment for
  server-to-server calls only; it is never sent to or accepted from the
  frontend.

## 3. Configuration

### `desktop/config.yaml`

Paths are relative to `desktop/` or use `~` for home (see the file in the repo):

```yaml
app_name: "AION Desktop Agent"
workspace_dir: "desktop_workspace"
allowed_dirs:
  - "~/Desktop"
  - "desktop_workspace"
oauth_dir: "~/.aion" # OAuth tokens live here (never in git)
voice:
  stt: "whisper" # "whisper" | "vosk" | "web"
  tts: "edge" # "edge" | "pyttsx3"
browser:
  headless: true
  default_path: "http://localhost:3000"
logs:
  level: "INFO"
  file: "logs/aion_desktop.log"
agent:
  port: 8080 # secret is NOT here — env AION_AGENT_SECRET only
```

### `desktop/.env.example`

```env
AION_AGENT_PORT=8080
# The bridge refuses to start with an empty or "change-me-in-production" secret.
AION_AGENT_SECRET=change-me-in-production
STT_MODEL_SIZE=small
```

### Backend approval environment (`apps/api/.env`)

| Variable                       | Default                                                                                                  | Purpose                                                                                                                        |
| ------------------------------ | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `AION_APPROVAL_DB_PATH`        | `` (in-memory)                                                                                           | SQLite path for the approval ledger + audit log. Set a real file (e.g. `/data/aion_approvals.db`) for durability.              |
| `AION_APPROVAL_TTL_SECONDS`    | `300`                                                                                                    | How long a pending approval stays approvable before it expires (expired requests never run).                                   |
| `AION_AGENT_BRIDGE_URL`        | `http://127.0.0.1:8080`                                                                                  | Local agent bridge base URL.                                                                                                   |
| `AION_AGENT_SECRET`            | ``                                                                                                       | Shared secret for backend→bridge calls. Must match the bridge's own env. Server-side only; **never** exposed to the frontend.  |
| `AION_BRIDGE_TIMEOUT_SECONDS`  | `30`                                                                                                     | Per-request timeout for bridge calls.                                                                                          |
| `AION_PROTECTED_DESKTOP_TOOLS` | `desktop_open_app,desktop_screenshot,browser_navigate,browser_screenshot,file_read,file_write,file_copy` | Comma-separated tools that always require explicit human approval. `desktop_list_apps` is exempt (read-only).                  |
| `AION_APPROVAL_DISPATCH_ASYNC` | `1`                                                                                                      | `1`: dispatch approved actions in a background task (approve returns `202` immediately). `0`: dispatch inline (used by tests). |

## 4. Running the MVP

1. Start backend (port 8000)
2. Start frontend (port 3000)
3. Start local agent bridge (port 8080): `cd desktop && export AION_AGENT_SECRET='your-secure-secret' && python -m aion_desktop.bridge`
4. Open dashboard → Chat / Tasks (a dedicated Desktop tab is planned, not built yet)
5. Request a desktop action through the approval API, e.g.:
   `curl -X POST http://localhost:8000/api/desktop/execute -H 'Content-Type: application/json' -d '{"tool":"file_write","parameters":{"path":"desktop_workspace/hello.txt","content":"hi"}}'`
   — chat-driven desktop control (chat message → pending approval) is planned, not built yet
6. Protected desktop actions enter the **approval queue** (tasks page) and
   raise an alert; nothing runs until you click **Approve**. An approved
   action executes exactly once under a one-time bridge grant; **Reject**
   is terminal and the linked task is marked failed.

---

## 5. Notes for you

- **Playwright browser install**: `python -m playwright install chromium`
- **Whisper model download**: `pip install openai-whisper`, then `whisper` will download a model on first use
- **PyAutoGUI**: works on macOS with accessibility permissions — you'll be prompted to allow it in System Settings → Privacy & Security → Accessibility
