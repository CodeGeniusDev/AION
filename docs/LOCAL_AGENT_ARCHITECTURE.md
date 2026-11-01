# AION — Local Agent Architecture

## 1. Overview

The local agent is a **Python process** that lives next to AION. AION's tool system calls it. The local agent does actual work on your Mac: browser, desktop, files, voice, social.

**Security model:** AION → (HTTP, auth token) → Local Agent → (allowlisted paths, headless browser, OAuth2) → your Mac

## 2. Directory layout

```
desktop/
├── aion_desktop/
│   ├── __init__.py
│   ├── config.py               # Load config.yaml + .env
│   ├── cli.py                  # CLI wrapper (run via: python -m aion_desktop.bridge)
│   ├── bridge.py               # Local HTTP server (FastAPI) on 8080
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py             # Tool protocol
│   │   ├── desktop.py          # PyAutoGUI + screencapture
│   │   ├── browser.py          # Playwright
│   │   ├── files.py            # copy, read, write, upload
│   │   ├── voice.py            # STT + TTS
│   │   └── social.py           # OAuth2 social post tools
│   ├── scheduler.py            # Background task scheduler (APScheduler)
│   ├── logger.py
│   └── utils.py
├── config.yaml
├── .env.example
├── requirements.txt
└── README.md
```

## 3. Tool protocol

Every tool must return:

```json
{
  "success": true,
  "result": { "anything": "object" },
  "task_id": "task-123",
  "duration_ms": 42
}
```

On failure:

```json
{
  "success": false,
  "error": "Human-readable error",
  "task_id": "task-123",
  "duration_ms": 5
}
```

AION's `ToolExecutor` already handles the pattern of executing tools and returning `ToolOutput`. The local agent implements the **Python-native** version of these tools so they can be called synchronously from the backend via subprocess or directly via an in-process bridge.

## 4. Security boundaries

1. **Path allowlist.** `files.py` only copies/reads/writes under `config.allowed_dirs`. Writes outside the allowlist are rejected.
2. **Headless browser by default.** `browser.py` sets `headless=True`. User must set `browser.headless: false` to see the browser.
3. **No shell execution.** `subprocess` is never used with `shell=True`. Commands are constructed as argument lists with strict allowlist.
4. **No account credentials in code.** All OAuth tokens are stored in `~/.aion/` files or the local agent DB, never in git.
5. **Audit logging.** Every tool call writes to `config.logs.file` plus cognitive memory.
6. **Human-in-the-loop approvals (two gates).** Protected desktop tools
   never execute on the shared secret alone. The backend approval ledger
   must hold a row a human explicitly approved (atomic `pending_approval →
running` claim, runs exactly once), _and_ the bridge must consume a
   matching one-time grant registered after that approval. A bridge
   restart drops all in-memory grants, so in-flight executions fail safely
   rather than running on a stale approval. See the sequence below.

### Approval grant sequence

```
Frontend                Backend (ledger + bridge client)          Bridge (127.0.0.1)
   |  POST /api/desktop/execute        |                                 |
   |---------------------------------->| create task + approval row      |
   |   202 pending_approval            | (status=pending_approval)       |
   |<----------------------------------|  ...never dispatches here...    |
   |                                   |                                 |
   |  human clicks Approve             |                                 |
   |  POST /api/approvals/{id}/approve |                                 |
   |---------------------------------->| atomic claim:                  |
   |                                   |   UPDATE ... WHERE status=      |
   |                                   |     'pending_approval' AND      |
   |                                   |     expires_at>now  (rowcount)  |
   |                                   | verify params_hash (SHA-256)    |
   |                                   |  POST /approvals/grant ------->| store sha256(token)
   |                                   |  X-Aion-Secret                 | (in-process, locked)
   |   202 status=running              |                                |
   |<----------------------------------| BackgroundTask dispatch:        |
   |                                   |  POST /tools/execute --------->| Gate1 secret (401)
   |                                   |  X-Aion-Secret + X-Aion-Approval| Gate2 consume grant
   |                                   |                                |  -> pop-before-execute
   |                                   |                                |  -> run executor ONCE
   |                                   |  result / audit 'executed' <---| replay => 403 already_consumed
```

## 5. Voice bridge (MVP-4)

```
User speaks → STT (whisper/vosk) → AION receives text → AION acts → TTS (edge/pyttsx3) → User hears
```

The voice tool is a **proxy** to the local agent. Voice input ends up as a normal chat message AION can act on.

## 6. How AION calls tools

AION's tool system already has a `tools/executor.py` with `ToolExecutor`. We extend the registry with **local tools** that either:

- Run a local Python script via subprocess (isolated), or
- Import the local agent module directly (in-process)

Recommendation: **in-process bridge via FastAPI** on port 8080. This keeps everything in one process, supports async, and is easier to debug. Security: the local agent binds to `127.0.0.1` only, requires the `AION_AGENT_SECRET` shared secret, **and** a one-time `X-Aion-Approval` grant registered by the backend only after a human approval (see section 4).
