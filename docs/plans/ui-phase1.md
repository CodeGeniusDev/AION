# AION — UI Phase 1 Plan: Foundation + Header + Profile (1A–1F)

Branch: `abdullah` (PR #1 still OPEN → continue here per directive).
Discipline: inspect → plan → small conventional commits, each passing gates.

## 1A Audit — baseline evidence (raw counts)

- Hardcoded white/hex color sites (`grep -rnE "bg-white|bg-\[#|text-\[#|border-\[#|#[0-9a-fA-F]{6}" apps/web/components apps/web/app`): **120 sites in 21 files**.
  - Of these, **65 are in `app/globals.css`** and are _legitimate_ — they are the token
    definitions themselves (`:root` + `[data-theme=…]` blocks). The real sweep target is
    the remaining **55 sites in 20 component/page files** → must reach ~0.
  - Top offenders after globals.css: `chat/aion-message.tsx` (9), `desktop/desktop-view.tsx` (6),
    `ui/status-badge.tsx` (4), `dashboard/dashboard-view.tsx` (4), `chat/chat-view.tsx` (4).
- Header controls today (`components/layout/top-navigation.tsx`): mobile menu (works,
  opens drawer), GlobalSearch (works, ⌘K + keyboard nav — client-side, to be upgraded to
  `/api/search` in 1E), theme toggle (works, `useTheme` — needs monitor icon for system
  - Settings/Profile same hook), NotificationsPopover (works, real `/api/alerts` — needs
    created_at/link/deep-links/relative-time/useNotifications in 1C), Settings link (works,
    hidden below `md` — must be reachable via user menu on mobile), ProfileMenu (works,
    real workspace name — replaced by /api/profile data in 1D).
- Routes: `/profile` **exists** (app/profile/page.tsx + components/profile/profile-view.tsx,
  built on /api/settings + /health — to be rebuilt on /api/profile in 1D). Backend has
  `/api/alerts`, `/api/settings`, `/api/conversations` (list), `/api/memories/records/search`.
  **No `/api/search`, no `/api/profile`** — both are additive new endpoints in 1D/1E.
- Duplicate "New Task": sidebar.tsx:133 AND dashboard-view.tsx:69 + tasks-view.tsx:98 →
  keep sidebar, remove page-header duplicates (directive 1C).
- Settings are **process-lifetime in-memory** (`models/settings.py` docstring) — lost on
  restart; 1D persists them in the new SQLite store.
- Pre-session WIP (uncommitted, from the earlier Phase-1 frontend pass): theme foundation,
  dependency-free dropdown, search popover, notifications popover, profile page, token
  sweep (162→120). Plan: absorb into 1B/1C/1E commits per sub-step scope, not as one blob.

## 1B Theme system

- Tokens already exist in globals.css (`--surface/--shell/--sidebar/--border/--text/
--muted-text/--primary/soft-*` + dark block) and tailwind mapping. Finish the list:
  surface-2, scrollbar, progress track, input/select/placeholder, status colors;
  `color-scheme` via `:root[data-theme]`.
- Replace all 55 component hex/white sites with tokens (justify remainders: shadow
  rgba() values and the settings toggle knob are intentionally theme-independent).
- ThemeProvider (exists, `aion-theme` localStorage, no-flash script in layout.tsx):
  add Settings sync (PUT /api/settings theme) + legacy "dim"→"dark" mapping at read time;
  Light/Dark/System everywhere (drop Dim UI). Backend: theme Literal already extended
  additively to include "dark" (backward compatible).
- Known-defect files to re-check in dark: dashboard cards (recent-task-row,
  agent-activity-row, summary-card, system-health-card, aion-status-banner), chat
  (aion-message, processing-state), status-badge, empty-state, form controls.
- Verification: Playwright sweep 11 routes × light/dark with computed-luminance
  assertion (no visible surface bg luminance > 0.8 in dark) + body-text contrast ≥ 4.5:1;
  screenshots → `apps/web/test-results/screenshots/` (git-ignored via test-results/).

## 1C Header

- Theme button: sun/moon/monitor by preference state, aria, persisted (existing hook).
- Alerts backend (additive): `created_at` already stored in SQLite `alerts` table →
  expose on AlertItem (`created_at: str = ""`, `link: str | None = None` — defaults keep
  old clients valid); set link at alert creation sites (/tasks?open=ID, /desktop?approval=ID).
- `hooks/useNotifications.ts`: 15s poll, pause when hidden, refetch on focus/local action;
  transport swappable to SSE in Phase 2.
- Popover: latest 8, tone icons, relative time, click→mark read + deep-link, per-item
  delete (needs DELETE /api/alerts/{id} — check existing, add if missing), mark-all,
  "9+" cap, hidden at 0, View all → /alert (absolute path — fixes `href="alert"` bug),
  empty/error states.
- User menu: real profile name/initials/avatar color from /api/profile (1D data; before
  1D lands, from settings workspace_name), Desktop approvals with real pending count
  (GET /api/approvals exists), theme segmented control, app version from /health.
  No Sign out (no session API). Below `sm`: menu carries theme + settings + profile links.
- Keyboard: Esc, click-outside, focus return, ArrowUp/Down in menus, aria roles
  (existing dependency-free dropdown extended — no new deps).
- Remove duplicate "New Task" from dashboard/tasks page headers (keep sidebar).

## 1D Profile + persistent settings (backend additive)

- `memory/profile_store.py` — SQLite, clones AlertStore pattern; path
  `AION_PROFILE_DB_PATH` env, default `apps/api/.data/profile.db` (git-ignored);
  conftest forces temp path. No seeded rows.
- `GET/PUT /api/profile` — single-workspace profile row: display_name(1-60),
  username(slug), email(optional, validated), role, timezone(IANA), bio(≤200),
  avatar_color(preset palette enum). 404/`{configured:false}` on first run — never a
  fake default person.
- Settings persistence: PUT /api/settings writes through to the same store
  (GET prefers stored over in-memory default). Backward compatible.
- `useProfile` context: single fetch shared by header + greeting + profile page;
  "Set up profile" in header when unset; greeting falls back to "Hello".
  Remove hardcoded "Abdullah"/"AION Workspace" display fallbacks (workspace_name is
  user-editable data, not a display fallback).
- Profile page: identity form (dirty tracking, inline validation, unsaved guard) +
  real counts (tasks total/completed/failed via /api/tasks status fields, approvals via
  /api/approvals, workflow runs, memory records, conversations, member-since from store
  created_at) + runtime card (/health). Notification toggles + default view move to /
  stay in Settings only; Profile links there.

## 1E Global search

- `GET /api/search?q=&limit=` (new route file `routes/search.py`): min 2 chars,
  max 100, tenant-aware, groups tasks/approvals/agents/workflows/memory/conversations
  (title+messages)/alerts/schedules; `{type,id,title,subtitle,href,snippet,score}`;
  lexical case-insensitive, prefix > word-boundary ranking; redaction applied to
  snippets (1F module reused); tests incl. tenant isolation + redaction.
- Frontend: global-search.tsx repointed to /api/search (AbortController, 200ms debounce
  kept), recent searches (localStorage, clearable), "/" focus, scope chips All|This page,
  `usePageSearch` for live per-page filtering, quick actions client-side, deep-links
  `/tasks?open=ID` etc. — every target page handles its param (add where missing:
  tasks, memory?record, chat?c, workflows?open, agents?open, desktop?approval).
- Mobile: search icon → full-width overlay.

## 1F Secret guard

- `security/redaction.py` (new package): table-driven detector + `[REDACTED: kind]`
  rewriter (password forms, Bearer, AIza/sk- keys, PEM blocks, long hex/base64,
  Luhn cards). Applied in chat route BEFORE conversation store / memory / alerts /
  logs / approval params / Gemini request.
- `ChatResponse.warnings: list[str] = []` (additive). Chat UI warning banner.
- Tests ≥25 incl. false positives; assert persisted text and mocked-model input.

## Files touched (est.)

Backend new: routes/search.py, routes/profile.py, memory/profile_store.py,
security/redaction.py + tests. Backend edits: models/settings.py (Literal, done),
models/notifications.py (+created_at/link), models/chat.py (+warnings), routes/alerts.py,
routes/chat.py (redaction), routes/settings.py (persist), main.py (2 routers),
memory/alert_store.py (link on create), services/\* (alert link sites), conftest.py.
Frontend new: hooks/useNotifications.ts, hooks/usePageSearch.ts, providers/
profile-provider.tsx, e2e specs. Frontend edits: all 20 hex-offender files, header
components, profile page, settings view, deep-link pages, types/index.ts, services/api.ts.
Docs: this file, PROGRESS.md, PR_NOTES.md, .env.example (AION_PROFILE_DB_PATH).

## Risks

- Chat pipeline insertion point (1F) could alter existing chat test expectations →
  keep redaction inert on normal text; run full backend suite before commit.
- Luminance assertion may false-positive on images/radii → scope assertion to
  elements with a token-class background, document exclusions.
- Alert `link` site coverage depends on where alerts are created (task_service,
  dashboard events) → additive default keeps old rows valid.
- Deep-link params need per-page `useSearchParams` + Suspense boundary in App Router
  (build-time CSR bailout) → verify with `next build`.
- Uncommitted pre-session WIP must be split cleanly into sub-step commits; gates run
  per commit, so intermediate states must each be green.
- Gemini quota: chat E2E against live API is quota-risky → prefer mock-level asserts,
  one live check only if quota allows.

## Dependency budget

No new packages. Existing dependency-free dropdown is extended for menus/search
(listbox roles, focus return, arrow navigation). Radix allowance (≤2) not used.
