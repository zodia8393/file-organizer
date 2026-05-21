#!/usr/bin/env bash
# One-shot scheduled Claude Code execution for app_organizer
# Self-removes from crontab after execution

set -euo pipefail

LOGDIR="/workspace/app_organizer/logs"
mkdir -p "$LOGDIR"
LOGFILE="$LOGDIR/scheduled_$(date +%Y%m%d_%H%M%S).log"

echo "[$(date)] Starting scheduled Claude Code execution..." | tee "$LOGFILE"

# Remove this entry from crontab (one-shot)
crontab -l 2>/dev/null | grep -v 'run-scheduled.sh' | crontab - 2>/dev/null || true

# Source NVM for claude CLI access
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

# Run Claude Code with the prompt
cd /workspace/app_organizer
claude --print \
  --model claude-sonnet-4-6 \
  --max-turns 30 \
  "$(cat /workspace/app_organizer/.claude-prompt.md)" \
  2>&1 | tee -a "$LOGFILE"

echo "[$(date)] Scheduled execution completed." | tee -a "$LOGFILE"
