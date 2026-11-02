# AION — Session Progress Report (Phases 0–7)

Sole-engineer session on branch `abdullah` → `origin abdullah` (PR #1 to
`main`). 60 commits ahead of main. No merges, no force-pushes, no history
rewrites. Every phase below ended with the four mandatory gates plus a live
E2E run; raw outputs were pasted into the per-phase reports and PR #1
comments.

## Phase table

| Phase | Delivered | Key commits | Commands run (per phase) | Actual results |
|---|---|---|---|---|
| 0 — Cleanup | MVP.sh hardened (venv before pip, `--dry-run` touches nothing, `--mock-servers` removed, never overwrites `desktop/config.yaml`, `~`-relative paths); docs made honest; `desktop_list_apps` comma-parsing fix + test | `1c9ac66`, `e187619`, `c65a963`, `7ebefae`, `bb78ac9` | `shellcheck MVP.sh`, `bash -n MVP.sh`, real `--dry-run`, pytest, secret/history scan | shellcheck + bash -n clean; dry run created nothing; `desktop_list_apps` parses 1 line → N apps; history grep: no secrets/.env/logs//Users paths entered by this session |
| 1 — Real Workflow entity | SQLite workflow store (CREATE IF NOT EXISTS, seed-once), GET/POST `/api/workflows`, `/api/workflows/{id}`, `/run` via existing WorkflowRunner (manual, model-safe agents), real `runs` counter + derived `state`; frontend create/run UI | `3a45681`…`f11e46d` (8 commits) | pytest (22 new), tsc, lint, live E2E | Live: create → run → counter 0→1 → state completed; all gates green |
| 2 — Chat-driven approval requests | Create-only chat pipeline (`services/chat_approval.py`: heuristic layer + optional LLM classifier with NO tool declarations), pending approvals from chat, chat reply links to queue; approve endpoint physically unreachable from chat path | `4fd1e5b`…`81d911a` (6 commits) | pytest (32 new incl. injection attempts), tsc, lint, live E2E | Injection tests: "approve it yourself"/spoofed grants/JSON tool-calls never approve or execute; live: chat → pending → approve → file written once → full audit chain |
| 3 — Desktop tab | `/desktop` page: approval queue, task history with output, bridge health indicator, recent audit events; loading/error/empty states; Playwright smoke test; `/api/desktop/health` probe | `98eed8a`…`b1d6971` (7 commits) | pytest, tsc, lint, Playwright smoke, live E2E | Smoke test passes; live health probe reflects bridge up/down; newest-first audit fixed in `d134ae6` |
| 4 — Browser tools (Playwright) | Real Playwright execution behind approval: `browser_navigate`/`browser_screenshot` with headless-from-config, URL policy (no `file://`, blocked loopback ports, allowlist/denylist), redirect re-validation, screenshots workspace-only (path derived, never supplied) | `815efc5`…`650661d` (5 commits) | `python -m playwright install chromium`, pytest w/ local fixture HTML, tsc, lint, live E2E | Chromium installed; navigate+screenshot executed only after approve; off-policy URLs refused; all gates green |
| 5 — Scheduler integration | SQLite schedule store (tenant-scoped, restart-safe), schedule CRUD behind auth/WRITE_ROLES, `ScheduleRunner` thread (opt-in `AION_SCHEDULER_ENABLED=1`) that at fire time ONLY calls `request_execution` — pending approvals, never auto-execute; backpressure, fake-clock tests; Schedules panel on Desktop tab | `cbd1600`…`f613a8d` (7 commits) | pytest (11 schedule tests incl. tenant isolation + restart persistence), tsc, lint, live E2E | Live: interval schedule fired → pending → approve → file written once → completed; audit actor=scheduler with params_hash; backend restart preserved rows |
| 6 — Voice (graceful degradation) | Browser Web Speech dictation → normal chat path (Phase 2 rules apply to voice); `/api/voice/status` + `/api/voice/say` (optional edge-tts, availability-as-data, never a crash); bridge voice executors honor config.yaml backends, request params ignored; "Speak" on answers | `bdde84c`…`eefc7f6` (6 commits) | pytest (7 + 5 new, mocked backends), tsc, lint, live E2E | Live: real 33,264-byte MPEG layer III synthesized; dictated chat → pending → reject → no file; ExplodingBridge test proves voice never touches bridge/ledger; whisper/vosk NOT installed (>1 GB torch — owner decision) |
| 7 — Social (scaffolding, dry-run only) | `social_post` protected approval-gated tool; official-API provider specs (Meta Graph FB/IG, Pinterest v5, TikTok Content Posting); OAuth2 state + PKCE S256; `TokenVault` `~/.aion` 0600 (symlink/perm refusal, redacted reprs); live requires config AND env secret AND vault token; chat whitelist + heuristic | `def7689`…`766c870` (6 commits, incl. `6d83f31` requirements honesty fix) | pytest (16 + 10 new, socket-blocked zero-network proof), tsc, lint, live E2E | Live: chat → pending → approve → bridge dry-run 0.1 ms, full audit chain, `~/.aion` never created, 0 secret/token matches in logs; spoofed `"live": true` inert |

## Final gate state (as of HEAD `766c870`)

```
apps/api  $ python -m pytest tests/ -q   → 456 passed
desktop   $ python -m pytest tests/ -q   → 63 passed
apps/web  $ npx tsc --noEmit             → exit 0
apps/web  $ npm run lint                 → clean (max-warnings=0)
```

Invariant tests: Gemini function declarations remain exactly
`calculator, text_analysis, current_datetime`; desktop tools reachable only
through the approval ledger + one-time bridge grant (proven again in
`test_desktop_approvals`, `test_chat_approvals`, `test_social`,
`test_schedules`, `test_bridge_security`).

## What the push/PR looks like

- `git log --oneline` HEAD: `766c870` (full 60-commit list in PR #1 and above).
- `git status --short`: clean (only gitignored scratch: `output/`, logs,
  `desktop_workspace/`).
- Pushes this session: `f613a8d..eefc7f6` (Phase 6), `eefc7f6..766c870`
  (Phase 7); earlier phases pushed per phase. PR #1 updated with a
  per-phase comment for every phase.

## Remaining risks / known gaps (honest)

1. **Social live posting is dark** — code path exists but unexercised until
   credentials + app review land; dry-run is the only reachable mode today
   (by construction, and tested that way).
2. **TikTok public posts need app review** — unreviewed apps can only post
   privately; the provider spec says so.
3. **Instagram needs an image URL** hosted publicly — the chat heuristic
   captures a URL if present, but the official flow (container → publish)
   is two calls; the scaffold builds the container request only.
4. **Voice STT is Chromium/Safari-only** (Web Speech API); Firefox users see
   no mic button. Local-model STT remains an owner install (whisper > 1 GB).
5. **Scheduler fires only while the API process runs** — missed windows
   during downtime are skipped, not back-filled (next tick recalculated).
6. **Auth is opt-in** — routes honor `get_current_principal`/`WRITE_ROLES`
   but with auth disabled everything is the `default` tenant, as before.
7. Pre-existing, untouched: `.qoder/**` IDE artifacts in history (one
   contains an absolute /Users path from the repo's initial commit — not
   introduced by this session).

## Owner (me) manual actions required

- **Meta**: create a Graph API app + FB Page; generate a Page access token
  with `pages_manage_posts`; for Instagram, link a Business/Creator account
  and pass app review for `instagram_content_publish`.
- **Pinterest**: create a developer app; request `pins:write` +
  `board_access`; note the target board id.
- **TikTok**: register a Content Posting API app and complete review before
  public direct posting is possible.
- Put the resulting client IDs/secrets in `desktop/.env`
  (`AION_SOCIAL_*` — template in `desktop/.env.example`), never in git;
  complete the OAuth exchange so tokens land in `~/.aion` (0600); then flip
  `social.live_enabled: true` in `desktop/config.yaml` deliberately.
- Optional: install `openai-whisper`/`vosk` if local (offline) dictation is
  wanted (>1 GB download), and grant macOS Accessibility/Screen Recording
  permissions when PyAutoGUI-grade input or non-`screencapture` paths are
  built (future phase).
- AION root `.env` / `apps/api/.env`: set a strong `AION_AGENT_SECRET` and
  decide `AION_REQUIRE_AUTH` before anything leaves localhost.
