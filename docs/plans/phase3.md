# Phase 3 Plan — Desktop tab (`/desktop`)

## Goal
A real Desktop page in the dashboard (sidebar entry, same design system)
showing: the live approval queue, desktop task history with output, a bridge
health indicator, and recent audit events. Loading / error / empty states for
each section. A Playwright smoke test covers the page.

## Backend (apps/api) — minimal additive surface
- `services/desktop_bridge_client.py`: new `health()` method — plain GET to
  the bridge `/health` (no secret header needed for health, no token, short
  3 s timeout), raises `BridgeError` on transport failure like the other
  methods.
- `routes/desktop.py`: new `GET /api/desktop/health` returning
  `DesktopHealthResponse { reachable: bool, status: str | null }`. Returns
  200 with `reachable=false` when the bridge is down — the frontend must be
  able to show "bridge offline" without the request itself failing. No
  secret, no token, no tool data ever included. Readable by any
  authenticated role (same policy as `GET /api/approvals`).
- `models/approval.py`: add `DesktopHealthResponse` (additive only).
- Tests: `tests/test_desktop_approvals.py` additions — health endpoint
  reachable/unreachable mapping, and proof the response body contains no
  secret-like fields.

## Frontend (apps/web)
- `services/api.ts`: `getDesktopHealth()`, `getAudit(limit)` (existing
  `GET /api/audit` contract, `items` shape).
- `types/index.ts`: `DesktopHealth` interface (additive).
- `components/approvals/approval-queue.tsx`: optional `fallback` prop so the
  Desktop page can render an explicit "queue is clear" empty state (tasks
  page keeps today's hide-when-empty behavior — backward compatible).
- `components/ui/status-badge.tsx`: extend palette for `pending_approval`,
  `rejected`, `expired` (no contract change; existing statuses untouched).
- New `components/desktop/desktop-view.tsx`: PageHeader + 2-column responsive
  grid (stacks on mobile):
  1. Bridge health card (green Offline/Online pill, last check, retry).
  2. Approval queue (reuses `ApprovalQueue`, 5 s polling already built in).
  3. Desktop task history: `GET /api/approvals` (all statuses, newest first);
     each row shows tool, sanitized params, status badge, and for terminal
     rows the linked task output via `GET /api/tasks/{id}` (capped at the 8
     most recent rows, fetched in parallel; output shown truncated with
     title-attr full text).
  4. Recent audit events: `GET /api/audit?limit=12`, timeline of
     ts/event/approval_id/actor (detail only when present; server already
     redacts).
  Every section: loading skeleton, error state with retry, empty state.
- New `app/desktop/page.tsx` (AppShell wrapper, same as tasks page).
- `components/layout/sidebar.tsx`: Desktop item (Monitor icon) in the System
  group before Research.
- `e2e/smoke.spec.ts`: `/desktop` renders (heading visible, no crash even
  when the API is unreachable — the error states must prove that).

## Endpoints touched
- New: `GET /api/desktop/health`
- Reused as-is: `GET /api/approvals`, `POST /api/approvals/{id}/approve|reject`,
  `GET /api/audit`, `GET /api/tasks`, `GET /api/tasks/{id}`

## Security invariants (unchanged)
- No approve/dispatch path is added anywhere; the page only consumes existing
  human-gated endpoints. `ApprovalQueue` is the single place a human decision
  is submitted.
- Health response carries zero secret/token material; bridge URL/secret stay
  server-side.
- Gemini tool declarations remain calculator/text_analysis/current_datetime.

## Risks
- Playwright smoke runs against `npm run dev` without a backend: the page
  must render its error states, not crash → this is exactly what the smoke
  test asserts.
- `GET /api/approvals` returns newest-first already; if not, history order
  is fixed client-side (sort by created_at desc) defensively.
