# AION Desktop Approval System — Threat Model

Scope: the human-in-the-loop gate around protected desktop tools
(`POST /api/desktop/execute` → approval ledger → bridge one-time grant →
`/tools/execute`). Verified by `apps/api/tests/test_desktop_approvals.py`,
both `test_bridge_security.py` suites, and a manual end-to-end run against
the live bridge with a real `file_write`.

## What the approval system protects against

| Threat | Mitigation (proven in E2E) |
| --- | --- |
| Agent/prompt-injection-driven desktop actions | No protected tool executes without a human clicking Approve; the execute endpoint only ever creates a `pending_approval` row (202) and provably never dispatches. |
| Double execution / re-approval races | Atomic conditional-SQL claim (`rowcount`-guarded); second approve → 409 even under a two-thread race; the executed file was written exactly once (mtime/MD5 unchanged after replay). |
| Replayed bridge requests | Grants are single-use: consumed atomically *before* the executor runs; a byte-identical replay gets 403 `already_consumed`. |
| Leaked shared secret alone | `X-Aion-Secret` by itself gets 403 on `/tools/execute` — the secret is necessary but no longer sufficient. |
| Approve/execute parameter swap (TOCTOU) | Execution runs the stored approved snapshot, re-hashed (SHA-256) at claim time; tampering → 500 + `failed`, executor never called. |
| Stale approvals | Pending rows expire after `AION_APPROVAL_TTL_SECONDS` (late approve → 410); a bridge restart drops all in-memory grants, so in-flight dispatches fail safe (never partially execute or retry on an old approval). |
| Unauthorized approvers | Role-gated (`admin`/`user`; `readonly` → 403, missing/invalid key → 401 when `AION_REQUIRE_AUTH=1`), tenant-scoped (cross-tenant → 404, no existence leak). |
| Secret leakage through data planes | Ledger stores only token hashes; API responses, alerts and the append-only audit log carry sanitized parameters (`content` → `{redacted, length, sha256}`) — confirmed by grep over the live audit output. |
| Approved-but-escaping file paths | Defense in depth *after* approval: the bridge enforces its own path allowlist; `/tmp/...` and a workspace symlink pointing outside were both refused (`failed` + reason recorded, no file created). A human approving the wrong path still cannot escape the allowlist. |

## What it does NOT protect against

- **A compromised backend.** The ledger trusts the backend process; it
  holds `AION_AGENT_SECRET` and is the only client allowed to register
  grants. Code that runs *inside* the backend can register a grant for any
  tool and approve its own ledger rows without a human. The gate is a
  barrier against the agent layer, tool replay, and external callers — not
  against the server itself being malicious.
- **A local user (or process) holding the secret.** Anyone who can read
  `AION_AGENT_SECRET` and reach `127.0.0.1:8080` can register grants and
  execute tools directly, bypassing the ledger and the human. On-machine
  code with the same user privileges is equally trusted by design; anyone
  with those privileges can also read the allowlisted directories anyway.
- **A mistaken human.** Approval authorizes the *action*, not its wisdom.
  The approver sees a sanitized preview — `file_write` content is shown
  redacted (length + SHA-256 only), so the human approves file bodies
  sight-unseen and relies on the bridge allowlist for blast radius.
  Approvals are also as privileged as the API keys allowed to click them;
  there is no MFA or two-person rule on approve.
- **Transport eavesdropping.** Both hops are plain HTTP on localhost
  (no TLS); it protects against remote attackers, not on-box network taps.
- **Durability gaps.** With the default in-memory stores a restart loses
  pending approvals and grants (actions stall, never run wrongly); set
  `AION_APPROVAL_DB_PATH` for a durable ledger. A backend crash *between*
  claim and dispatch leaves the row `running` and the action never executed
  — fail-safe, but it requires a fresh approval request; there is no
  automatic retry (by design: retrying is exactly what the grant prevents).
- **Anything outside the desktop-tool path.** Chat, memory, research and
  the other APIs have no approval gate; social/OAuth tools are out of scope
  until they exist.

## Explicit non-goals

TLS, per-user OAuth, chat-driven approval requests (agent → pending
approval from `/api/chat`), tamper-proof *remote* attestation of who
approved, and protection of the local filesystem from the local user.
