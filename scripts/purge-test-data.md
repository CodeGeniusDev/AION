# Purging test pollution from live AION data stores

Phase 2A moves Playwright onto its own isolated API + web stack with per-run
temp SQLite files. That stops NEW pollution, but the existing live stores may
already contain rows created by pre-isolation E2E runs (test tasks, alerts,
conversations, seeded profile rows) mixed in with your real data. This
document describes how **you** clean those files. The agent will never delete
your data on its own.

## What the E2E suite writes and where

Nothing under Playwright touches these files any more — every test boots an
isolated API on port **3124** with `AION_*_DB_PATH` env vars pointing into a
fresh `mkdtempSync(tmpdir(), "aion-e2e-")` directory that is discarded when
the run ends. See `apps/web/playwright.config.ts` for the wiring.

| Store                     | Env var                     | Local default                              | Docker default                    |
|---------------------------|-----------------------------|--------------------------------------------|-----------------------------------|
| Cognitive memory          | `AION_MEMORY_DB_PATH`       | `:memory:` (empty string in `config.py`)   | `/data/aion_memory.db`            |
| Alerts + task alerts      | shares `AION_MEMORY_DB_PATH`| `:memory:`                                 | `/data/aion_memory.db`            |
| Approval ledger + audit   | `AION_APPROVAL_DB_PATH`     | `:memory:`                                 | `/data/aion_approvals.db`         |
| Profile + settings        | `AION_PROFILE_DB_PATH`      | `apps/api/.data/profile.db`                | `/data/aion_profile.db`           |
| Workflow entity store     | `AION_WORKFLOW_DB_PATH`     | `:memory:`                                 | (not mounted)                     |
| Schedule store            | `AION_SCHEDULE_DB_PATH`     | `:memory:`                                 | (not mounted)                     |
| Conversations             | (none — always in-memory)   | `:memory:`                                 | `:memory:`                        |
| Task store                | (none — always in-memory)   | `:memory:`                                 | `:memory:`                        |

In-memory stores are lost on process restart. **Only `profile.db` and the two
Docker volumes persist across restarts.** That is the surface area you need to
inspect.

## Deciding what is real vs test pollution

Test rows created by the pre-2A suite have these signatures:

- Titles containing `phase1`, `Phase 1`, `zzqx`, `test-`, `seed-`,
  `quantum-widget`, `thispage-scoped-task`, `deep-link-probe-message`,
  `cleanup`, `setup-state`, `header-and-dashboard`.
- Task `id`s beginning with `test-` (the fixture endpoint uses this prefix).
- Alerts whose `link` is `/tasks?open=x` or similar hard-coded E2E routes.
- Profile row with `username` equal to `e2e`, `tester`, `setup-state-user`,
  `ada`/`phase2a` (from Phase 2A's own fixtures — safe to delete after a run).

Your real data will not have these markers. Grep for them before deleting:

```bash
# Inspect profile
sqlite3 apps/api/.data/profile.db \
  "SELECT username, display_name FROM profile;"

# Inspect memory-derived alerts + episodic memory (only if you set the path)
[ -f "$AION_MEMORY_DB_PATH" ] && sqlite3 "$AION_MEMORY_DB_PATH" \
  "SELECT id, title FROM tasks WHERE id LIKE 'test-%' OR title LIKE 'phase1%' LIMIT 20;"

# Inspect the approval ledger
[ -f "$AION_APPROVAL_DB_PATH" ] && sqlite3 "$AION_APPROVAL_DB_PATH" \
  "SELECT request_id, tool_name, status FROM approvals LIMIT 20;"
```

## Safe cleanup recipes

**Option A — nuke just the profile (most common pollution).** Reset the
browser-facing profile while leaving memory and approvals intact:

```bash
sqlite3 apps/api/.data/profile.db "DELETE FROM profile; DELETE FROM settings;"
```

**Option B — surgical row deletes.** Remove only rows that match the pollution
markers above, one table at a time. Always run the `SELECT` variant first to
preview what would be deleted.

```bash
# Preview, then delete, tasks created by the old E2E suite.
sqlite3 "$AION_MEMORY_DB_PATH" \
  "SELECT id, title FROM tasks WHERE id LIKE 'test-%' OR title LIKE 'phase1%';"
sqlite3 "$AION_MEMORY_DB_PATH" \
  "DELETE FROM tasks WHERE id LIKE 'test-%' OR title LIKE 'phase1%';"
```

**Option C — full reset of one store.** Only after **backing up** and
confirming the store contains nothing you care about:

```bash
cp "$AION_MEMORY_DB_PATH" "$AION_MEMORY_DB_PATH.bak.$(date +%s)"
rm "$AION_MEMORY_DB_PATH"
# Restart the API — the next boot recreates the schema.
```

**Never delete the approval ledger** without reading each row first. The
ledger is the security-critical record of every desktop tool decision; if you
need to prune test noise from it, delete only rows whose `payload` matches the
pollution markers above, and keep the audit log entries paired with them.

```bash
sqlite3 "$AION_APPROVAL_DB_PATH" \
  "SELECT request_id, tool_name, substr(payload,1,80) FROM approvals \
   WHERE payload LIKE '%phase1%' OR payload LIKE '%test-%' OR payload LIKE '%zzqx%';"
```

## Docker deployment

Under `docker compose`, the two persistent files live on the `aion_data`
volume. Inspect without stopping the API:

```bash
docker compose exec api ls -la /data
docker compose exec api sqlite3 /data/aion_memory.db \
  "SELECT id, title FROM tasks WHERE id LIKE 'test-%';"
```

To delete, either run the same `sqlite3` command with a `DELETE`, or stop the
stack, take a snapshot with `docker run --rm -v aion_aion_data:/data alpine
cp -r /data /backup-data`, then proceed. **Never** `docker compose down -v` —
that wipes the whole volume including your real data.

## What Phase 2A guarantees going forward

- Playwright boots its own API on `127.0.0.1:3124` with `AION_MEMORY_DB_PATH`,
  `AION_APPROVAL_DB_PATH`, `AION_PROFILE_DB_PATH`, `AION_WORKFLOW_DB_PATH`,
  `AION_SCHEDULE_DB_PATH` all pointing into a fresh `aion-e2e-*` temp dir.
- `reuseExistingServer: false` on both webServer entries — the suite can never
  silently attach to your developer stack.
- `AION_TEST_MODE=1` only in that subprocess. Your `apps/api` process never
  sees the flag, so `/api/_test/*` returns 404 in every real deployment (see
  `apps/api/tests/test_test_fixture_phase2a.py::TestTestModeGuard`).
- After a run the temp dir becomes garbage; you can safely
  `rm -rf "$(find "$TMPDIR" -maxdepth 1 -name 'aion-e2e-*' -type d)"` if you
  want to reclaim disk immediately (macOS auto-purges `$TMPDIR` on reboot).

If you ever see writes land in a non-temp file, that is a bug in
`playwright.config.ts` — please open an issue with the file path and the
`grep -n TEMP_ROOT apps/web/playwright.config.ts` output.
