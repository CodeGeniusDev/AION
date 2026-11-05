#!/usr/bin/env bash
# ==============================================================================
# AION — MVP BUILD & DEPLOYMENT SCRIPT
#
# This script helps you build the AION Desktop Operating System MVP step by step.
# It:
#   1. Checks prerequisites (Python, Node, Playwright, PyAutoGUI, etc.)
#   2. Asks you which feature to build first
#   3. Creates the project structure (desktop/ agent, docs/)
#   4. Installs dependencies (Python + Node)
#   5. Starts backend + frontend
#   6. Shows first test cases + next steps
#
# Usage:
#   chmod +x MVP.sh
#   ./MVP.sh
#
# IMPORTANT SECURITY NOTE:
#   - This script only creates local files, installs Python/Node packages,
#     and starts local dev servers. Nothing dangerous is run automatically.
#   - Social media tools require OAuth2 — this script will NOT ask for passwords.
#   - Browser automation runs headless (no visible browser) unless you change it.
# ==============================================================================

set -euo pipefail

# ---- Colors ------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ---- Globals ------------------------------------------------------------------------
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AION_DIR="${REPO_DIR}"
DESKTOP_DIR="${AION_DIR}/desktop"
DOCS_DIR="${AION_DIR}/docs"
BACKEND_PORT=8000
FRONTEND_PORT=3000
AGENT_PORT=8080

# ---- Helpers ------------------------------------------------------------------------
print_status()  { echo -e "${GREEN}[✓]${NC} $1"; }
print_warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
print_error()   { echo -e "${RED}[✗]${NC} $1"; }
print_info()    { echo -e "${BLUE}[•]${NC} $1"; }
print_header()  { echo ""; echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"; echo -e "${CYAN}║${NC}  ${1}"; echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"; echo ""; }

log_file() {
  # Dry runs must create/modify nothing — MVP_BUILD.log included.
  if [ "${DRY_RUN}" = true ]; then return 0; fi
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "${REPO_DIR}/MVP_BUILD.log"
}

# Activate the repo virtualenv BEFORE any pip install (prevents installing
# into system Python). Exits with guidance when the venv is missing.
ensure_venv() {
  if [ ! -f "${REPO_DIR}/.venv/bin/activate" ]; then
    print_error "Python virtual environment not found at ${REPO_DIR}/.venv"
    print_info "Create it with: python3 -m venv .venv && .venv/bin/pip install -r apps/api/requirements.txt"
    exit 1
  fi
  # shellcheck source=/dev/null
  source "${REPO_DIR}/.venv/bin/activate"
  print_status "Activated .venv (python3 -> $(command -v python3))"
}

# ---- Step 1: Check prerequisites ----------------------------------------------------
check_prerequisites() {
  print_header "Step 1/7 — Checking prerequisites"

  local missing=()

  # Python
  if command -v python3 &>/dev/null; then
    local py_version
    py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    print_status "Python ${py_version} found"
  else
    print_error "Python 3 is not installed. Install from https://python.org"
    missing+=("python3")
  fi

  # Node + npm
  if command -v node &>/dev/null && command -v npm &>/dev/null; then
    print_status "Node.js $(node -v), npm $(npm -v)"
  else
    print_error "Node.js + npm are not installed. Install from https://nodejs.org"
    missing+=("node/npm")
  fi

  # Python packages
  for pkg in playwright pynput pyautogui aiohttp aiosignal asyncio pydantic; do
    if python3 -c "import ${pkg}" &>/dev/null; then
      print_status "Python package '${pkg}' found"
    else
      print_warn "Python package '${pkg}' is missing (not critical for MVP-1). Install with: pip install ${pkg}"
    fi
  done

  # Node packages (playwright)
  if [ -d "${REPO_DIR}/apps/web/node_modules" ]; then
    print_status "Node packages already installed"
  else
    print_warn "Node packages not installed yet (will run npm install later)"
  fi

  if [ ${#missing[@]} -gt 0 ]; then
    print_error "Missing: ${missing[*]}"
    exit 1
  fi

  print_status "All critical prerequisites met."
}

# ---- Step 2: Ask user what to build ---------------------------------------------------
ask_build_order() {
  print_header "Step 2/7 — What would you like to build first?"

  echo "A) Core MVP (verify AION runs + tasks + local tool registry)"
  echo "B) Desktop automation (Playwright browser + PyAutoGUI)"
  echo "C) Voice assistant (STT + TTS bridge)"
  echo "D) Social media integrations (Facebook/Instagram/TikTok/Pinterest)"
  echo "E) Full orchestration (scheduler + alerts + mobile companion)"
  echo "F) Everything at once (full MVP)"
  echo ""
  print_info "Defaulting to full MVP (all features)"
  echo "To build specific components, edit this script and skip unwanted steps."
}

# ---- Step 3: Create project structure --------------------------------------------------
create_structure() {
  print_header "Step 3/7 — Creating project structure"

  if [ "${DRY_RUN}" = true ]; then
    print_info "[dry-run] would run: mkdir -p desktop/{aion_desktop/{tools,schemas},desktop_workspace,logs,scripts} docs/"
    return 0
  fi

  # desktop/ agent
  mkdir -p "${DESKTOP_DIR}/aion_desktop"
  mkdir -p "${DESKTOP_DIR}/aion_desktop/tools"
  mkdir -p "${DESKTOP_DIR}/aion_desktop/schemas"
  mkdir -p "${DESKTOP_DIR}/desktop_workspace"
  mkdir -p "${DESKTOP_DIR}/logs"
  mkdir -p "${DESKTOP_DIR}/scripts"

  # Docs
  mkdir -p "${DOCS_DIR}"

  # Keep existing docs as-is, we just added docs/

  print_status "Created:"
  echo "  ${DESKTOP_DIR}/"
  echo "  ${DESKTOP_DIR}/aion_desktop/"
  echo "  ${DESKTOP_DIR}/aion_desktop/tools/"
  echo "  ${DESKTOP_DIR}/aion_desktop/schemas/"
  echo "  ${DESKTOP_DIR}/desktop_workspace/"
  echo "  ${DESKTOP_DIR}/logs/"
  echo "  ${DESKTOP_DIR}/scripts/"
  echo "  ${DOCS_DIR}/  (you have the MVP plan + deployment + architecture docs)"

  log_file "Created project structure"
}

# ---- Step 4: Install dependencies -------------------------------------------------------
install_dependencies() {
  print_header "Step 4/7 — Installing dependencies"

  local mode="${1}"

  # pip must land in the repo venv, never system Python.
  if [ "${mode}" != "node-only" ]; then
    ensure_venv
  fi

  if [ "${mode}" = "python-only" ]; then
    print_status "Installing Python dependencies (audio/video tools may take a while)"
    pip install --upgrade pip
    pip install pynput pyautogui aiohttp aiosignal pydantic psutil
    if ! pip install openai-whisper 2>/dev/null; then
      print_warn "Whisper may need additional system dependencies (see docs/DEPLOYMENT.md)"
    fi
    print_status "Python dependencies installed."
  elif [ "${mode}" = "node-only" ]; then
    print_status "Installing Node dependencies in apps/web/"
    cd "${REPO_DIR}/apps/web"
    npm install
    print_status "Node dependencies installed."
  else
    print_status "Installing Python dependencies (audio/video tools may take a while)"
    pip install --upgrade pip
    pip install pynput pyautogui aiohttp aiosignal pydantic psutil
    if ! pip install openai-whisper 2>/dev/null; then
      print_warn "Whisper may need additional system dependencies (see docs/DEPLOYMENT.md)"
    fi

    print_status "Installing Node dependencies in apps/web/"
    cd "${REPO_DIR}/apps/web"
    npm install
    print_status "Node dependencies installed."
  fi
}

# ---- Step 5: Create config files ---------------------------------------------------------
create_config_files() {
  print_header "Step 5/7 — Creating configuration files"

  if [ "${DRY_RUN}" = true ]; then
    print_info "[dry-run] would create desktop/config.yaml (only if missing) and desktop/.env.example (only if missing)"
    return 0
  fi

  # desktop/config.yaml — never overwrite an existing (possibly edited) config.
  if [ -f "${DESKTOP_DIR}/config.yaml" ]; then
    print_warn "desktop/config.yaml already exists — keeping it (not overwriting)."
  else
    # Paths are relative to desktop/ (or ~) — resolved by aion_desktop/config.py.
    cat > "${DESKTOP_DIR}/config.yaml" << EOF
# AION Desktop Agent configuration
# Copy to config.local.yaml for local overrides (git-ignored)

app_name: "AION Desktop Agent"
workspace_dir: "desktop_workspace"

# Allowed directories for file operations (security boundary)
allowed_dirs:
  - "~/Desktop"
  - "desktop_workspace"

# OAuth tokens are stored in ~/.aion/ (never in git)
oauth_dir: "~/.aion"

# Voice bridge
voice:
  stt: "whisper"        # "whisper" | "vosk" | "web"
  tts: "edge"           # "edge" | "pyttsx3"

# Browser automation (MVP-2)
browser:
  headless: true        # Set to false to see the browser open
  default_path: "http://localhost:3000"

# Desktop control (MVP-2)
desktop:
  capture_enabled: true # Enable screen captures

# Logging
logs:
  level: "INFO"
  file: "logs/aion_desktop.log"

# Local agent bridge port. The secret is NOT stored in this file:
# it is read from the AION_AGENT_SECRET environment variable only
# (no --secret CLI flag, to keep it out of shell history).
agent:
  port: 8080
EOF
    print_status "Created ${DESKTOP_DIR}/config.yaml"
  fi

  # desktop/.env.example — also keep-if-present
  if [ -f "${DESKTOP_DIR}/.env.example" ]; then
    print_warn "desktop/.env.example already exists — keeping it."
  else
    cat > "${DESKTOP_DIR}/.env.example" << 'EOF'
# Copy to .env and fill in real values (git-ignored)
# AION_AGENT_SECRET must be a real secret — the bridge refuses to start
# with an empty or "change-me-in-production" value.
AION_AGENT_PORT=8080
AION_AGENT_SECRET=change-me-in-production
EOF
    print_status "Created ${DESKTOP_DIR}/.env.example"
  fi

  log_file "Created config files"
}

# ---- Step 6: Start backend + frontend ------------------------------------------------------
start_servers() {
  print_header "Step 6/7 — Starting servers"

  if [ "${MOCK_SERVERS}" = true ]; then
    print_info "MOCK SERVERS mode: NOT starting uvicorn / next dev — servers are skipped."
    print_info "To actually start them, run without --mock-servers (or: npm run dev at the repo root)."
    return 0
  fi

  ensure_venv

  print_warn "Starting backend (FastAPI, port ${BACKEND_PORT})..."
  cd "${AION_DIR}/apps/api"
  uvicorn main:app --reload --port "${BACKEND_PORT}" &
  BACKEND_PID=$!
  echo "${BACKEND_PID}" > "${REPO_DIR}/.backend.pid"
  print_status "Backend started (PID ${BACKEND_PID})"

  sleep 2

  print_warn "Starting frontend (Next.js, port ${FRONTEND_PORT})..."
  cd "${AION_DIR}/apps/web"
  npm run dev -- --port "${FRONTEND_PORT}" &
  FRONTEND_PID=$!
  echo "${FRONTEND_PID}" > "${REPO_DIR}/.frontend.pid"
  print_status "Frontend started (PID ${FRONTEND_PID})"

  sleep 3

  print_status "Backend health check..."
  if curl -s "http://localhost:${BACKEND_PORT}/health" | grep -qE "(healthy|degraded)"; then
    print_status "Backend is healthy."
  else
    print_warn "Backend may still be starting — check manually."
  fi

  print_status "Open in your browser:"
  echo "  Dashboard: http://localhost:${FRONTEND_PORT}/dashboard"
  echo "  API docs:  http://localhost:${BACKEND_PORT}/docs"
  echo ""
}

# ---- Step 7: Show test cases --------------------------------------------------------------
show_test_cases() {
  print_header "Step 7/7 — MVP test cases"

  echo "Run these to verify your setup:"
  echo ""
  echo "  1. Open http://localhost:3000/dashboard"
  echo "  2. Open http://localhost:8000/docs"
  echo "  3. Desktop actions go through the human approval queue (no auto-execution):"
  echo "       curl -X POST http://localhost:8000/api/desktop/execute \\"
  echo "         -H 'Content-Type: application/json' \\"
  echo "         -d '{\"tool\":\"file_write\",\"parameters\":{\"path\":\"desktop_workspace/hello.txt\",\"content\":\"hi\"}}'"
  echo "     then Approve it on the Tasks page (or POST /api/approvals/{id}/approve)."
  echo "  4. Check the Tasks page for the approval queue and task history."
  echo ""
  print_info "Chat-driven desktop requests (chat -> pending approval) are planned, not built yet."
  echo ""
  print_info "MVP is now running. Next steps:"
  echo "  - Read docs/AION_MVP_PLAN.md for the full roadmap"
  echo "  - Enable browser.headless: false in desktop/config.yaml to see the browser"
  echo "  - Start the local agent bridge (single documented command):"
  echo "      cd desktop && export AION_AGENT_SECRET='your-secure-secret' && python -m aion_desktop.bridge  # port ${AGENT_PORT}"
  echo "  - Add social tools in desktop/aion_desktop/tools/social.py"
  echo "  - Add voice via desktop/aion_desktop/tools/voice.py"
  echo ""
}

# ---- Cleanup ----------------------------------------------------------------------------
cleanup() {
  if [ -f "${REPO_DIR}/.backend.pid" ]; then
    local pid
    pid=$(cat "${REPO_DIR}/.backend.pid")
    if kill -0 "${pid}" &>/dev/null; then
      kill "${pid}" 2>/dev/null || true
    fi
  fi
  if [ -f "${REPO_DIR}/.frontend.pid" ]; then
    local pid
    pid=$(cat "${REPO_DIR}/.frontend.pid")
    if kill -0 "${pid}" &>/dev/null; then
      kill "${pid}" 2>/dev/null || true
    fi
  fi
  print_status "Servers stopped."
}

trap cleanup EXIT

# ---- Main ---------------------------------------------------------------------------------
# Options (parsed from $@)
DRY_RUN=false
MOCK_SERVERS=false

usage() {
  echo "Usage: $0 [--dry-run] [--mock-servers]"
  echo "  --dry-run       Show steps without executing them"
  echo "  --mock-servers  Use mocked servers (skip actual uvicorn/npm start)"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --mock-servers)
      MOCK_SERVERS=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

main() {
  print_header "AION MVP BUILD SCRIPT"

  echo "This script will build and deploy the AION Desktop Operating System MVP."
  echo ""
  echo "You can stop at any time by pressing Ctrl+C."
  echo ""

  if [ "$DRY_RUN" = true ]; then
    print_info "DRY RUN mode: steps will be shown but not executed."
  fi
  if [ "$MOCK_SERVERS" = true ]; then
    print_info "MOCK SERVERS mode: servers will be mocked, not started."
  fi

  check_prerequisites
  ask_build_order
  create_structure
  if [ "$DRY_RUN" = false ]; then
    install_dependencies "full"
  else
    print_info "Step 4 (install_dependencies) skipped in dry-run mode."
  fi
  create_config_files
  if [ "$DRY_RUN" = false ]; then
    start_servers
  else
    print_info "Step 6 (start_servers) skipped in dry-run mode."
  fi
  show_test_cases

  echo "MVP BUILD COMPLETE."
  echo ""
  print_status "Next steps:"
  echo "  1. Run this script again without --dry-run to actually build"
  echo "  2. Read docs/AION_MVP_PLAN.md for the full roadmap"
  echo "  3. Ask me 'what to build next' to continue with MVP-2/MVP-3"
  echo ""
}

main "$@"
