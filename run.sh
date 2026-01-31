#!/bin/bash
# Kōan — Main run loop
# Pulls missions, executes them via Claude Code CLI, commits results.

set -euo pipefail

KOAN_ROOT="$(cd "$(dirname "$0")" && pwd)"
INSTANCE="$KOAN_ROOT/instance"

if [ ! -d "$INSTANCE" ]; then
  echo "[koan] No instance/ directory found. Run: cp -r instance.example instance"
  exit 1
fi

# Config via env vars (or defaults)
MAX_RUNS=${KOAN_MAX_RUNS:-20}
INTERVAL=${KOAN_INTERVAL:-300}
PROJECT_PATH=${KOAN_PROJECT_PATH:-"/path/to/your-project"}

count=0

echo "[koan] Starting. Max runs: $MAX_RUNS, interval: ${INTERVAL}s"

while [ $count -lt $MAX_RUNS ]; do
  echo "[koan] Run $((count + 1))/$MAX_RUNS — $(date '+%Y-%m-%d %H:%M:%S')"

  # Pull latest instance state
  cd "$INSTANCE" && git pull --rebase origin main 2>/dev/null || true

  # Check usage budget
  claude -p "Read $INSTANCE/usage.md and $INSTANCE/config.yaml.
    If budget is exceeded or close to the stop threshold, write 'BUDGET_EXCEEDED' to /tmp/koan-status and stop.
    Otherwise write 'OK' to /tmp/koan-status." \
    --allowedTools Read,Write,Glob 2>/dev/null || true

  if [ -f /tmp/koan-status ] && grep -q "BUDGET_EXCEEDED" /tmp/koan-status; then
    echo "[koan] Budget exceeded. Stopping."
    break
  fi

  # Execute next mission
  claude -p "You are Kōan. Load $INSTANCE/soul.md for your personality.
    Load $INSTANCE/memory/ for context continuity.
    Check $INSTANCE/missions.md for the next Pending task.
    If no pending task, do autonomous exploration of $PROJECT_PATH.
    Execute the mission. Write your report in $INSTANCE/journal/.
    Update $INSTANCE/missions.md status.
    If you have a message for the human, append it to $INSTANCE/outbox.md." \
    --allowedTools Bash,Read,Write,Glob,Grep,Edit

  # Commit instance results
  cd "$INSTANCE"
  git add -A
  git diff --cached --quiet || \
    git commit -m "koan: $(date +%Y-%m-%d-%H:%M)" && \
    git push origin main 2>/dev/null || true

  count=$((count + 1))

  if [ $count -lt $MAX_RUNS ]; then
    echo "[koan] Sleeping ${INTERVAL}s..."
    sleep $INTERVAL
  fi
done

echo "[koan] Session complete. $count run(s) executed."
