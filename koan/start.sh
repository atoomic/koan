#!/bin/bash
# Kōan — Unified Launcher
# Starts both the agent loop (run.sh) and the messaging bridge (awake.py)
# in a single terminal. CTRL-C gracefully stops both.
#
# Usage: make start
#        ./koan/start.sh

set -euo pipefail

# --- Resolve KOAN_ROOT ---
if [ -z "${KOAN_ROOT:-}" ]; then
  # Auto-detect: start.sh lives in koan/, KOAN_ROOT is its parent
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  export KOAN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

INSTANCE="$KOAN_ROOT/instance"
if [ ! -d "$INSTANCE" ]; then
  echo "Error: No instance/ directory found. Run: cp -r instance.example instance"
  exit 1
fi

# --- Use venv python if available ---
PYTHON="python3"
[ -f "$KOAN_ROOT/.venv/bin/python3" ] && PYTHON="$KOAN_ROOT/.venv/bin/python3"
export PYTHONPATH="$KOAN_ROOT/koan"

# --- Color codes ---
if [ -t 1 ]; then
  _C_RESET='\033[0m'
  _C_BOLD='\033[1m'
  _C_DIM='\033[2m'
  _C_CYAN='\033[36m'
  _C_MAGENTA='\033[35m'
  _C_GREEN='\033[32m'
  _C_RED='\033[31m'
  _C_YELLOW='\033[33m'
else
  _C_RESET='' _C_BOLD='' _C_DIM=''
  _C_CYAN='' _C_MAGENTA='' _C_GREEN='' _C_RED='' _C_YELLOW=''
fi

# --- PIDs of child processes ---
RUN_PID=""
AWAKE_PID=""
STOPPING=false

cleanup() {
  if [ "$STOPPING" = true ]; then
    return
  fi
  STOPPING=true

  echo ""
  echo -e "${_C_BOLD}${_C_CYAN}[koan]${_C_RESET} Shutting down..."

  # Signal both children
  [ -n "$RUN_PID" ] && kill "$RUN_PID" 2>/dev/null
  [ -n "$AWAKE_PID" ] && kill "$AWAKE_PID" 2>/dev/null

  # Give them a moment to clean up
  local timeout=5
  local waited=0
  while [ $waited -lt $timeout ]; do
    local still_running=false
    [ -n "$RUN_PID" ] && kill -0 "$RUN_PID" 2>/dev/null && still_running=true
    [ -n "$AWAKE_PID" ] && kill -0 "$AWAKE_PID" 2>/dev/null && still_running=true
    [ "$still_running" = false ] && break
    sleep 1
    waited=$((waited + 1))
  done

  # Force kill if still alive
  [ -n "$RUN_PID" ] && kill -9 "$RUN_PID" 2>/dev/null || true
  [ -n "$AWAKE_PID" ] && kill -9 "$AWAKE_PID" 2>/dev/null || true

  # Wait for processes to be fully reaped
  [ -n "$RUN_PID" ] && wait "$RUN_PID" 2>/dev/null || true
  [ -n "$AWAKE_PID" ] && wait "$AWAKE_PID" 2>/dev/null || true

  echo -e "${_C_BOLD}${_C_CYAN}[koan]${_C_RESET} Stopped."
}

trap cleanup INT TERM

# --- Print combined startup banner ---
"$PYTHON" -c "from app.banners import print_startup_banner; print_startup_banner()" 2>/dev/null || true

echo -e "${_C_BOLD}${_C_GREEN}Starting Kōan...${_C_RESET}"
echo ""

# --- Start the messaging bridge (awake.py) ---
echo -e "${_C_MAGENTA}[bridge]${_C_RESET} Starting messaging bridge..."
(
  cd "$KOAN_ROOT/koan"
  KOAN_ROOT="$KOAN_ROOT" PYTHONPATH="$KOAN_ROOT/koan" "$PYTHON" app/awake.py 2>&1 | \
    while IFS= read -r line; do
      echo -e "${_C_DIM}${_C_MAGENTA}[bridge]${_C_RESET} $line"
    done
) &
AWAKE_PID=$!

# Brief pause to let the bridge initialize before the agent loop starts
sleep 1

# --- Start the agent loop (run.sh) ---
echo -e "${_C_CYAN}[agent]${_C_RESET} Starting agent loop..."
(
  "$KOAN_ROOT/koan/run.sh" 2>&1 | \
    while IFS= read -r line; do
      echo -e "${_C_CYAN}[agent]${_C_RESET} $line"
    done
) &
RUN_PID=$!

echo ""
echo -e "${_C_BOLD}${_C_GREEN}Both processes running.${_C_RESET} Press ${_C_BOLD}CTRL-C${_C_RESET} to stop."
echo ""

# --- Wait for either process to exit ---
# If one dies, we shut down the other too.
while true; do
  # Check if either process has exited
  if [ -n "$RUN_PID" ] && ! kill -0 "$RUN_PID" 2>/dev/null; then
    wait "$RUN_PID" 2>/dev/null
    RUN_EXIT=$?
    echo -e "${_C_YELLOW}[koan]${_C_RESET} Agent loop exited (code $RUN_EXIT). Stopping bridge..."
    [ -n "$AWAKE_PID" ] && kill "$AWAKE_PID" 2>/dev/null
    [ -n "$AWAKE_PID" ] && wait "$AWAKE_PID" 2>/dev/null || true
    break
  fi

  if [ -n "$AWAKE_PID" ] && ! kill -0 "$AWAKE_PID" 2>/dev/null; then
    wait "$AWAKE_PID" 2>/dev/null
    AWAKE_EXIT=$?
    echo -e "${_C_YELLOW}[koan]${_C_RESET} Bridge exited (code $AWAKE_EXIT). Stopping agent loop..."
    [ -n "$RUN_PID" ] && kill "$RUN_PID" 2>/dev/null
    [ -n "$RUN_PID" ] && wait "$RUN_PID" 2>/dev/null || true
    break
  fi

  sleep 2
done

echo -e "${_C_BOLD}${_C_CYAN}[koan]${_C_RESET} Session ended."
