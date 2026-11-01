# Phase 0 Plan — Cleanup (no features)

## Scope
1. `MVP.sh` correctness & safety fixes.
2. Honest docs: `AION_MVP_PLAN.md` checkbox + test counts, `DEPLOYMENT.md` demo line.
3. `desktop_list_apps` output parsing fix + test.
4. Git-history secret/log/abs-path verification.

## MVP.sh (files: `MVP.sh`)
- Activate `.venv` **before** any `pip install` (currently bare `pip` installs into
  system Python; venv only activated later inside `start_servers`).
- `--dry-run` must create/modify nothing: currently `create_structure` (mkdir),
  `create_config_files` (overwrites `desktop/config.yaml`) and `log_file`
  (writes `MVP_BUILD.log`) all run in dry-run. Gate every side-effecting step.
- `--mock-servers` is parsed but never used → make `start_servers` actually skip
  launching uvicorn/npm when set (and say so).
- Never overwrite an existing `desktop/config.yaml` (warn + keep).
- Generated config must use relative paths / `~` — not absolute home-directory paths.
- Remove the chat-driven desktop-control demo prompt ("type 'open Chrome…'")
  until Phase 2 ships.
- Checks: `bash -n`, shellcheck (via `shellcheck-py` in `.venv`), real `--dry-run`
  run with before/after proof that nothing was created/modified.

## Docs
- `AION_MVP_PLAN.md`: uncheck "Wire execute_tool into the chat flow" (planned,
  Phase 2); update the Testing row from **real** pytest output.
- `DEPLOYMENT.md` step 5: replace the chat-message demo that implies desktop
  control with the REST → approval-queue flow that actually exists.

## desktop_list_apps (file: `desktop/aion_desktop/bridge.py`)
- `osascript … get name of processes` returns ONE comma-separated line; current
  code splits on `\n` → `count` is always 1. Split on `,`, strip. Test asserts
  multiple parsed apps (executor mocked with canned stdout).

## Risks
- MVP.sh behavior change could break a user's flow → dry-run/mocks verified live.
- Test-count edits must come from a fresh full-suite run (paste raw output).
