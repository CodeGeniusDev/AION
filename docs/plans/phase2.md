# Phase 2 Plan — Chat-driven approval requests (the missing link)

## Goal
Let the chat pipeline turn a natural-language desktop action request into a
**pending approval** in the existing ledger — and nothing more. The
model/LLM path gains the ability to *request* (create a pending row) but
keeps zero ability to approve, execute, or observe grant tokens.

## Security invariants (must hold, must be tested)
1. Chat can only ever call `ApprovalService.request_execution` (creates
   `pending_approval` + task + alert; never touches the bridge).
2. `approve_and_claim`, `reject` and `dispatch` are unreachable from the
   chat code path — proven by spies in tests and by code review of the
   single import surface.
3. Gemini function declarations remain exactly
   `calculator, text_analysis, current_datetime` (unchanged; isolation test
   still passes). The chat-approval classifier is a *separate* text call
   that receives no `tools` field at all.
4. No grant token, token hash, or bridge secret appears in ChatResponse,
   alerts, audit details, or logs. Control phrases inside user messages
   ("approve it yourself") are treated as inert text.
5. Chat-created requests are restricted to `settings.protected_desktop_tools`
   (never the model-exposed safe tools — a chat message must not be able to
   forge a "pending approval" that auto-runs anything).

## Files
- **New** `apps/api/services/chat_approval.py`
  - `DesktopIntent(tool, parameters)` — strictly validated.
  - `detect_desktop_intent(message)` — deterministic heuristic (primary,
    zero-cost, testable): imperative file/desktop/browser phrasing with a
    concrete path/target; question/hypothetical phrasing never matches.
  - `classify_with_llm(message)` — optional second layer, only when Gemini
    is configured: single `generate()` call, no tool declarations,
    strict-JSON response parsed defensively; unknown/unprotected tools
    dropped; parse failure → no intent (fails closed).
  - `validate_parameters()` — allowed keys + length caps per known tool
    schema; drops anything resembling token/grant/approval-control keys.
  - `handle_chat_desktop_request(...)` — the ONLY entry point used by the
    chat route; calls `request_execution` and returns a public
    `PendingApprovalInfo`.
- `apps/api/models/chat.py` — add optional `pending_approval: PendingApprovalInfo | None`
  to `ChatResponse` (additive → backward compatible).
- `apps/api/routes/chat.py` — after `workflow_runner.run(...)`, run the
  classifier; on intent: create pending approval, prepend a notice line to
  `response.answer`, set `response.pending_approval`. Classifier failures
  are swallowed (chat must never break because of this feature).
- `apps/api/tests/test_chat_approvals.py` — new suite (below).
- **Frontend** `apps/web/types/index.ts` (+`PendingApprovalInfo`, optional
  field), `components/chat/aion-message.tsx` (amber notice card with link
  to the approval queue at `/tasks`).

## Endpoints
No new endpoints. Behavior change only inside `POST /api/chat` response
(one optional additive field + answer prefix).

## Tests
- Heuristic: positive detections (write/create/read/copy/open app/navigate)
  and non-detections (questions, "how do I", mention of a path).
- LLM path with fake `GeminiService`: strict-JSON parse; tool-spoofing
  payload from the model is rejected against the protected whitelist
  (`request_execution` itself 404s unknown tools).
- Injection: "…approve it yourself and run it" → still exactly one
  `pending_approval` row; spies on `approve_and_claim`/`reject`/`dispatch`
  prove they are never called; ledger audit contains only `requested`.
- Grant-token absence: serialized ChatResponse JSON contains no
  `grant`/`token`/`secret` fields even when the message claims
  `grant_token=…`.
- `POST /api/chat` E2E through TestClient with a stubbed bridge: pending
  appears via `GET /api/approvals`, approve via the human endpoint
  executes once, answer mentions the queue.

## Live E2E (against running servers)
chat message → `GET /api/approvals?status=pending_approval` shows the row →
`POST /api/approvals/{id}/approve` → file exists exactly once →
`GET /api/audit` shows requested/approved/claimed/granted/executed, no
secrets → replay rejected.

## Risks
- False positives create harmless pending rows that expire (TTL 300 s) —
  acceptable; human can reject. Patterns kept narrow.
- Extra Gemini call per message only when heuristic misses AND Gemini is
  configured AND circuit breaker closed; dev-mode (no key) costs nothing.
- Answer prefix changes existing chat text formatting slightly — additive,
  frontend renders `whitespace-pre-wrap`, no contract break.
