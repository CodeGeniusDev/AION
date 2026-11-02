# Phase 4 Plan — Browser tools (Playwright) behind approval

## Goal
Make `browser_navigate` and `browser_screenshot` real, safely: Playwright
Chromium launched by the bridge, every navigation checked against a URL
policy, screenshots confined to the workspace, and the approval gate
untouched (both tools remain protected; Gemini still sees only
calculator / text_analysis / current_datetime).

## Findings from inspection (current state)
- `desktop/aion_desktop/browser.py` is non-functional scaffolding:
  `BrowserManager.start()` is `async` but calls `run_until_complete`
  (crashes inside the bridge's running loop); `navigate()` calls
  `page.content_type()` / `page.status()` which don't exist in the
  Playwright API; `click()` references an undefined `started`; every
  action method opens a *fresh blank page*, so screenshot/click/fill
  would capture/operate on nothing.
- `bridge.py` holes:
  - `browser_navigate` honors `params["headless"]` — the *requester*
    can force a visible browser. Headless must come from config only.
  - `browser_screenshot` honors `params["output_path"]` unvalidated —
    arbitrary file write outside the workspace.
  - `browser_screenshot` ignores `params["url"]` even though the chat
    whitelist (`chat_approval.py`) and protected-tools default are
    built around `{url}`. Screenshotting a fresh blank page is useless.
- `desktop/requirements.txt` declares `playwright>=1.64,<2.0` but it is
  NOT installed in `.venv`. Node-side browser cache exists
  (`~/Library/Caches/ms-playwright/chromium-1243`), so
  `python -m playwright install chromium` should reuse or fetch the
  matching build (~130MB — under the 500MB stop threshold).
- Only `test_tool_executors.py` (subprocess-mocked) touches executors;
  no browser tests exist.

## Files to change
| File | Change |
|---|---|
| `desktop/aion_desktop/browser.py` | Fix `start()`/`navigate()`/`click()`/`screenshot()` against the real Playwright API; keep one *active page* per manager so navigate→screenshot compose; add `BrowserPolicy` (dataclass) + `UrlBlockedError`; add `browser_policy_from_config(config)`. |
| `desktop/aion_desktop/bridge.py` | `_executor_for` gains a `browser_policy` arg (default `None` → default-deny policy). `browser_navigate`: drop `params["headless"]` (config-driven headless in manager), validate URL. `browser_screenshot`: navigate to validated `url` first; ignore `output_path` param entirely — file always `workspace/browser-screenshot-<ts>.png`. Wire policy from config in `build_app`. |
| `desktop/config.yaml` + `DEFAULT_CONFIG` (`config.py`) | `browser.blocked_ports` list (3000, 8000, 8010, 8080, 8443, 3001…), `browser.allowlist`, `browser.denylist`. Keep `headless: true`. |
| `desktop/tests/test_browser_policy.py` | Pure-policy tests (no browser): schemes, localhost admin ports, allowlist/denylist precedence, malformed URLs. |
| `desktop/tests/test_browser_live.py` | Integration tests marked `skipif` (playwright or chromium missing): fixture HTML served on an ephemeral port → navigate real page, screenshot lands inside workspace, `file://` rejected before any browser launch, `localhost:8080` rejected. Executor-level tests monkeypatch `BrowserManager` to prove the *executors* enforce policy + ignore `output_path`/`headless` params. |
| `desktop/requirements.txt` | Already declares playwright — no change. Install into `.venv` + `playwright install chromium`. |

## URL policy (defaults, all overridable via config.yaml)
- Scheme must be `http` or `https`. `file:`, `chrome:`, `javascript:`,
  `data:`, `about:` etc. are always refused (not just "not allowed").
- Hostname `localhost` / `127.x` / `::1` / `0.0.0.0` is refused **only on
  blocked admin ports** (config list: 3000, 8000, 8010, 8080, 8443, 3001).
  Other local ports are allowed (dev fixture pages run on ephemeral ports).
- `denylist` (hostnames) always wins; `allowlist` (if non-empty) means
  only those hostnames may be visited.
- Navigation timeout enforced from `BrowserManager.timeout` (30s default).

## Threat model — what does NOT change
- Approval gate: `browser_navigate` / `browser_screenshot` remain in
  `AION_PROTECTED_DESKTOP_TOOLS`; execution still requires ledger
  approval + one-time bridge grant. No backend route changes.
- Gemini: function declarations remain calculator / text_analysis /
  current_datetime. Existing tests prove it; no new tool is registered
  in the API tool registry.
- Chat path: `chat_approval._ALLOWED_PARAMETERS` already caps `url` at
  1024 chars and `_FORBIDDEN_KEY` still drops token-ish keys. Policy
  enforcement lives at the bridge (execution time), so a crafted
  pending-approval URL is blocked *and audited as failed* — creation may
  happen, execution may not.
- Decisions: requester-supplied `headless` and `output_path` params are
  **ignored** (config/derived values only). This strengthens, never
  weakens, the boundary.

## browser_click / browser_type — deliberately NOT added
They would need: new entries in the protected-tools env default, API
registry + Gemini isolation tests, chat whitelist, and a *stateful*
session (click a button on a page navigated in a *previous* approved
call) which the current one-shot bridge architecture doesn't have. The
directive says "only if each is approval-gated and param-hash covered" —
the honest answer for this session is they aren't yet. Documented as
planned in docs; `BrowserManager` methods remain internal scaffolding.

## E2E (live)
1. Serve a local fixture HTML on an ephemeral port (python http.server).
2. Start bridge + API (proven recipe, 127.0.0.1 ports 8080/8010).
3. `POST /api/chat` "Navigate to http://127.0.0.1:<port>/fixture.html"
   → pending approval appears (Phase 2 path proves URL flows through).
4. Approve via `POST /api/approvals/{id}/approve` → task completes,
   navigation result (title/status) in task output.
5. Approve a `browser_screenshot` → PNG exists inside
   `desktop_workspace/`, size > 0, audit shows requested→executed, no
   grant token anywhere.
6. Negative: approve-time blocked URL (`file://…`) via direct
   `/tools/execute` with a valid grant → executor returns
   `success:false`, no browser launched, nothing written.

## Risks
- `playwright install chromium` may be blocked by network → STOP
  condition, report, tests degrade to skipif (honest "planned" docs).
- Sandbox flakiness launching Chromium (seen in Phase 3) → integration
  tests retry-tolerant / skippable; policy + executor logic fully
  tested without a browser.
- Changing `_executor_for` signature → only two call sites in
  `desktop/tests/*` + bridge itself; keep new arg keyword-with-default
  so existing tests pass unchanged.

## Gate checklist
pytest (apps/api full), pytest (desktop), `npx tsc --noEmit`,
`npm run lint`, live E2E above — raw output in the final report.
