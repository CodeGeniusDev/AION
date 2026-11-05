#!/usr/bin/env bash
# AION preflight — run before starting the stack for real-world use.
# Checks: non-default AION_AGENT_SECRET, persistent DB paths, free ports,
# .venv present, Playwright chromium installed, auth posture.
# Prints PASS/WARN/FAIL per check. NEVER prints any secret value.
# Exit code: 0 if no FAIL, 1 otherwise.
# Lint: shellcheck -x scripts/preflight.sh (install: pip install shellcheck-py)
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/apps/api/.env"

PASS=0; WARN=0; FAIL=0
ok()   { printf 'PASS %s\n' "$1"; PASS=$((PASS+1)); }
warn() { printf 'WARN %s\n' "$1"; WARN=$((WARN+1)); }
bad()  { printf 'FAIL %s\n' "$1"; FAIL=$((FAIL+1)); }

# Read one KEY from an env file without exporting or printing it.
env_lookup() {
  local key="$1" file="$2" line value
  [[ -f "$file" ]] || return 1
  line="$(grep -E "^[[:space:]]*${key}=" "$file" | tail -1 || true)"
  [[ -n "$line" ]] || return 1
  value="${line#*=}"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

# --- 1. Shared secret: present, long enough, not a known placeholder -----
secret="$(env_lookup AION_AGENT_SECRET "$ENV_FILE" || true)"
# Current shell env wins over the file (uvicorn reads both).
[[ -n "${AION_AGENT_SECRET:-}" ]] && secret="$AION_AGENT_SECRET"
if [[ -z "$secret" ]]; then
  bad "AION_AGENT_SECRET is empty — the bridge will refuse every call"
elif (( ${#secret} < 16 )); then
  bad "AION_AGENT_SECRET is set but too short (<16 chars) [value not shown]"
elif printf '%s' "$secret" | grep -qiE '^(change[-_ ]?me|your[-_ ]?secret|secret|replace[-_ ]?me|dev[-_ ]?secret|test|default|password123)'; then
  bad "AION_AGENT_SECRET looks like a placeholder — generate a real one [value not shown]"
elif (( ${#secret} < 32 )); then
  ok "AION_AGENT_SECRET set, >=16 chars (below 32 — consider a longer one) [value not shown]"
else
  ok "AION_AGENT_SECRET set, >=32 chars, non-placeholder [value not shown]"
fi

# --- 2. Persistent SQLite paths (empty = data lost on restart) -----------
for key in AION_MEMORY_DB_PATH AION_APPROVAL_DB_PATH; do
  value="$(env_lookup "$key" "$ENV_FILE" || true)"
  [[ -n "${!key:-}" ]] && value="${!key}"
  if [[ -z "$value" ]]; then
    warn "$key unset — state is in-memory and lost on restart"
  else
    dir="$(dirname "$value")"
    if [[ -d "$dir" || "$dir" == /* ]]; then
      ok "$key set to a persistent path"
    else
      warn "$key points at a directory that does not exist yet: $dir"
    fi
  fi
done

# --- 3. Ports free (8000 api, 3000 web, 8080 desktop bridge) -------------
for port in 8000 3000 8080; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    warn "port $port is already in use (something else is listening)"
  else
    ok "port $port free"
  fi
done

# --- 4. Python venv -------------------------------------------------------
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  ok ".venv present ($("$ROOT/.venv/bin/python" --version 2>&1))"
else
  bad ".venv missing — run: python3 -m venv .venv && .venv/bin/pip install -r apps/api/requirements.txt"
fi

# --- 5. Playwright chromium ----------------------------------------------
if ls "$HOME"/Library/Caches/ms-playwright/chromium-* >/dev/null 2>&1 \
  || ls "$HOME"/.cache/ms-playwright/chromium-* >/dev/null 2>&1; then
  ok "Playwright chromium installed"
else
  bad "Playwright chromium missing — run: npx playwright install chromium"
fi

# --- 6. Auth posture (informational) --------------------------------------
require_auth="$(env_lookup AION_REQUIRE_AUTH "$ENV_FILE" || true)"
[[ -n "${AION_REQUIRE_AUTH:-}" ]] && require_auth="$AION_REQUIRE_AUTH"
if [[ "$require_auth" == "1" ]]; then
  ok "AION_REQUIRE_AUTH=1 (authenticated)"
else
  warn "AION_REQUIRE_AUTH unset/0 — localhost-only mode; the API also logs this warning at startup if the bridge is reachable"
fi

printf '\nPreflight: %d PASS, %d WARN, %d FAIL\n' "$PASS" "$WARN" "$FAIL"
(( FAIL == 0 ))
