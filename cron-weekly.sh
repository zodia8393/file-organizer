#!/usr/bin/env bash
# 매주 금요일 /workspace 자동 정리
set -euo pipefail

LOGDIR="/workspace/app/organizer/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/cron_$(date +%Y%m%d_%H%M%S).log"

echo "[$(date)] Weekly workspace cleanup started" >> "$LOG"
cd /workspace/app/organizer
python3 -m organizer.cli apply \
  -s /workspace \
  -r config/workspace_rules.yaml \
  --confirm \
  >> "$LOG" 2>&1
echo "[$(date)] Done" >> "$LOG"
