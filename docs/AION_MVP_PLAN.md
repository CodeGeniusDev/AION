# AION — Desktop Operating System MVP: Full Build Plan

> **For:** Abdullah Abbad (AION owner)
> **Project:** AION — Artificial Intelligence Operating Nervous System
> **Goal:** Turn AION from an AI chat/multi-agent backend into a **desktop OS-like agent** that controls your Mac, browser, social accounts, and business work — with a voice assistant that feels human.
> **Created:** 2026-10-31
> **Status:** Planning + MVP script ready. Code implementation requires approval per file.

---

## 1. WHY THIS REALLY IS NECESSARY

AION right now is a **smart AI command center**: agents talk to each other, verify each other's output, remember things, and handle chat/agents/tasks/memory. But it has three gaps:

1. **Partial desktop control** — file operations and app launches now run through the approval-gated local bridge (chat → pending approval → human approves → executes once), but browser clicking, scheduling and social posting are not built yet.
2. **No social automation** — TikTok, Pinterest, and Facebook are manual today.
3. **No voice assistant** — AION can "talk" but cannot yet "listen" and act on voice commands.

The fix is not a rewrite. It is a **glue layer**: a local Python agent (in the same repo) that AION's tool system calls. AION stays the brain; this layer is the hands, eyes, and voice.

---

## 2. CURRENT STATE — What's REAL and What's DEMO

### Already real (code in repo)

| Area                | What exists                                                                                          |
| ------------------- | ---------------------------------------------------------------------------------------------------- |
| Backend             | FastAPI + Uvicorn + Pydantic + SQLite                                                                |
| Frontend            | Next.js App Router, TypeScript, Tailwind, shadcn_ui                                                  |
| Multi-agent         | Planner / Researcher / Critic / Memory agents                                                        |
| Agent routing       | Cognitive DNA registry + AgentRouter + DynamicBrainFormer                                            |
| Message bus         | CognitiveBus (in-process pub/sub, task-scoped)                                                       |
| Memory              | SQLite-backed Cognitive Memory (real persistent store)                                               |
| Workflows           | SQLite-backed Workflow entity; create + run via WorkflowRunner (manual mode, model-safe agents)      |
| Tools               | Calculator (safe AST eval), text_analysis, current_datetime, memory/knowledge providers              |
| Chat pipeline       | Dynamic Brain Formation → Agents → Cognitive Bus → Immune verification → Memory write-back           |
| Auth                | Opt-in API-key auth (`AION_REQUIRE_AUTH`), tenant resolution                                         |
| Rate limiting       | Per-IP + per-key rate limiter                                                                        |
| Observability       | Request ID/correlation IDs, structured logging, metrics                                              |
| Testing             | 428 backend tests + 9 desktop bridge tests + 5 Playwright e2e smoke tests                           |
| Docker              | Compose for web + api                                                                                |
| UI / responsiveness | Tailwind + Radix primitives; layout is mobile-responsive already (sidebar, top nav, responsive grid) |

### Demo / placeholder

| Area                  | Status                                                         |
| --------------------- | -------------------------------------------------------------- |
| External web research | Only static test corpus + internal memory. No live web source. |
| Voice assistant       | No STT/TTS module.                                             |
| Desktop automation    | No tools exist yet.                                            |
| Social media tools    | No tools exist yet.                                            |

### What AION has not built yet (capability gaps, not impossibilities)

- Open an app on your Mac
- Navigate a browser and click/type
- Upload a file to a website
- Post to Facebook / Instagram / TikTok / Pinterest — **planned via official APIs** (see MVP-3): Meta Graph API for Facebook/Instagram Pages, Pinterest API, TikTok Content Posting API (after app review). Requires a developer app + OAuth credentials from the owner.
- Take voice commands
- Run background tasks on a schedule

---

## 3. VISION — The Target Product

```
USER → Voice or typing → AION (FastAPI + Next.js dashboard)
                              ↓
                    AION Agent Brain
                    (Planner / Researcher / Critic / Memory)
                              ↓
         ↙──────────┬──────────┬──────────┬──────────┐
         ↓          ↓          ↓          ↓          ↓
   Desktop     Browser     Social     Business   Process
   control     control     control    automation  automation
         ↓          ↓          ↓          ↓          ↓
      Tools layer  Tools      Tools      Tools      Tools
      (Python)     (Playwright)  (OAuth  (Meta/TikTok/ (schedulers)
```

AION is the **brain**. The lower layer is the **hands**: tools that actually do things on your Mac.

---

## 4. MVP SCOPE — What we build first

### MVP-1 (today) — Core foundation

- [x] Verify AION runs end-to-end (backend + frontend + chat)
- [x] Add a persistent `tasks` table + `task_status` flow (pending → running → completed/failed)
- [x] Add a `local_tools` registry mapping tool names → Python scripts / functions
- [x] Chat → approval link (Phase 2): a chat message can *create* a pending approval for a protected desktop tool via the existing approval service. The model can never approve, execute, or see grant tokens — only the human queue (`/tasks` → `POST /api/approvals/{id}/approve`) executes. Gemini tool declarations remain calculator/text_analysis/current_datetime only.
- [x] "Desktop" tab in the dashboard (Phase 3): approval queue, desktop task history with real output, bridge health indicator and recent audit events at `/desktop`

### MVP-2 — Desktop automation (highest "wow")

- [ ] Python automation CLI: `aion-desktop`
- [ ] Browser control via Playwright (headless Chrome)
  - `desktop_open_app`
  - `browser_navigate`
  - `browser_type`
  - `browser_click`
  - `browser_screenshot`
  - `browser_upload_file`
- [ ] Desktop control via PyAutoGUI + screencapture
- [ ] File ops: copy, read, write
- [ ] Local voice bridge (STT + TTS)

### MVP-3 — Social media (planned, requires developer app + OAuth credentials from the owner)

Posting to social accounts **is possible via official APIs** — it is not impossible,
just not built yet and gated on owner-supplied credentials and app review:

- [ ] Facebook / Instagram: Meta Graph API for Pages (OAuth2)
- [ ] TikTok: TikTok Content Posting API (restricted, needs developer app review)
- [ ] Pinterest: Pinterest API (check ToS for the intended posting flow)
- [ ] `social_post(platform, payload)` tool
- [ ] `business_schedule(platform, post, time)` scheduler

### MVP-4 — Voice assistant

- [ ] STT: Whisper (local) or Web Speech API
- [ ] TTS: Edge TTS or pyttsx3 (local)
- [ ] Wake word / voice command parsing → same tool dispatcher
- [ ] Voice status output ("AION, done" style reply)

### Phase-5 — Full orchestration

- [ ] Task queue with scheduler
- [ ] Status UI per task
- [ ] Alerts and notifications
- [ ] Multi-tenant isolation (currently opt-in)

---

## 5. ARCHITECTURE — How the pieces fit

```
AION Codebase (this repo)
├── apps/web/            # Next.js dashboard (already responsive)
│   ├── app/
│   │   ├── chat/         # AI Chat (existing)
│   │   ├── tasks/        # Task list (existing)
│   │   ├── dashboard/    # Dashboard (existing)
│   │   ├── agents/       # Agent registry (existing)
│   │   ├── new: "desktop"/ # Desktop control tab
│   │   └── settings/     # Settings (existing)
│   └── components/...
├── apps/api/             # FastAPI backend (already real)
│   ├── orchestration/    # WorkflowRunner, AgentRouter, ResponseSynthesizer
│   ├── cognitive_bus/    # In-process pub/sub
│   ├── memory/           # SQLite Cognitive Memory (real)
│   ├── tools/            # Tool registry + executor (existing pattern)
│   ├── routes/           # API routes + Chat flow
│   └── tools/            # (add) local_desktop_tools.py, social_tools.py, voice_tool.py
└── desktop/              # NEW local agent (the "hands")
    ├── aion_desktop/
    │   ├── __init__.py
    │   ├── browser.py        # Playwright browser control
    │   ├── desktop.py        # PyAutoGUI + screencapture
    │   ├── files.py          # File ops
    │   ├── social.py         # Facebook/Instagram/TikTok/Pinterest OAuth tools
    │   ├── voice.py          # STT + TTS bridge
    │   ├── scheduler.py      # Background task scheduler (APScheduler)
    │   └── cli.py            # CLI entry point
    ├── config.yaml
    └── README.md
```

---

## 6. SECURITY — Non-negotiable rules

1. **No password sharing.** OAuth2 only for social accounts.
2. **No unattended browser.** Playwright headless by default. User must explicitly enable "visible" mode.
3. **Local scripts are path-restricted.** Only files under `~/Desktop/AION/` (or a config allowlist) can be read/written. No shell injection.
4. **All long-running tasks run as separate tasks** with status updates. Never block the chat.
5. **Rate limiting** applies to the local agent too.
6. **All actions logged.** Every tool call writes to cognitive memory and the task log.
7. **No cloud secrets.** Keep API keys in `apps/api/.env` / `desktop/config.yaml` (both git-ignored).
8. **Auth is opt-in by default.** Set `AION_REQUIRE_AUTH=1` in a real deployment.
9. **Human-in-the-loop desktop approvals (BUILT).** The audit's top
   security gap — protected desktop tools executing on the shared secret
   alone — is addressed. Every protected tool (`desktop_open_app,
desktop_screenshot, browser_navigate, browser_screenshot, file_read,
file_write, file_copy`) now requires an explicit human approval, gated
   by two independent checks: (1) a backend approval ledger with atomic
   exactly-once lifecycle transitions + an append-only audit log, and
   (2) a bridge one-time grant token consumed before execution. A leaked
   secret no longer means arbitrary desktop control, and no action can run
   twice or unapproved. See `README.md` → _Human-in-the-loop desktop tool
   approvals_ and `docs/LOCAL_AGENT_ARCHITECTURE.md` → _Approval grant
   sequence_. Chat-driven approval requests (chat → pending approval) shipped
   in Phase 2: the chat pipeline can only *create* pending approvals for
   protected tools; approval, dispatch and execution remain human/REST-only
   and the model never sees grant tokens.

---

## 7. FILE/FOLDER STRUCTURE CREATED

```
AION/
├── apps/
│   ├── web/              # Next.js (existing)
│   └── api/              # FastAPI (existing)
├── desktop/              # NEW local agent (MVP-2..4)
├── docs/                 # NEW — this documentation folder
└── ...
```

---

## 8. MVP SHELL SCRIPT — MVP.sh

`MVP.sh` does, in order:

1. Check dependencies (Python 3, Node, npm, Playwright, PyAutoGUI, openai-whisper, aiohttp)
2. Ask the user which feature to build first
3. Build the project structure (`desktop/` + docs)
4. Write `desktop/config.yaml` and `desktop/.env.example`
5. Install Python + Node dependencies
6. Start backend + frontend
7. Show first test cases + how to run

---

## 9. 30/60/90 DAY ROADMAP

### 30 Days — MVP-1 + MVP-2 (desktop automation)

- [x] WorkflowRunner + tasks table + local tool registry
- [ ] Browser control in Playwright
- [ ] Desktop control in PyAutoGUI
- [ ] File ops
- [ ] Voice bridge
- [x] Dashboard "Desktop" tab

### 60 Days — MVP-3 (social media)

- [ ] OAuth flows for Facebook, Instagram, TikTok, Pinterest
- [ ] `social_post` tool
- [ ] `business_schedule` tool
- [ ] Scheduler background service
- [ ] Notifications and alerts

### 90 Days — Full OS

- [ ] Task scheduler (cron-style)
- [ ] Multi-tenant isolation
- [ ] Advanced memory (tagging, filtering)
- [ ] Voice wake-word
- [ ] Production hardening + monitoring

---

## 10. WHAT WE WILL NOT BUILD IN THIS MVP

- Posting to live social accounts — planned, not impossible: requires official developer apps + OAuth credentials from the owner (Meta Graph API, Pinterest API, TikTok Content Posting API after app review). Deferred until credentials exist.
- Full desktop OS-level access (security risk; we scope to allowlisted paths)
- Sending emails automatically
- Multi-account social management
- Mobile app companion
- Video generation / complex AI training
