#!/usr/bin/env bash
# FCA monitoring pipeline - scheduled wrapper for scraper/run_pipeline.py.
#
# Usage:  scripts/fca_pipeline.sh [--method rule_based] [--upload --bucket gs://...]
#
# Logs to data/logs/pipeline_YYYYmmdd-HHMM.log. Set GROQ_API_KEY (or store it
# in ~/.groq/key) for the zero_shot method.
#
# Cron entry (every 6 hours; see README for the rationale):
#   0 */6 * * *  cd /home/you/fca_project && ./scripts/fca_pipeline.sh >> data/logs/cron.out 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python" ]; then
    PY="$ROOT/.venv/bin/python"
else
    PY="$(command -v python3)"
fi

LOG_DIR="$ROOT/data/logs"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d-%H%M)"
LOG_FILE="$LOG_DIR/pipeline_${STAMP}.log"

echo "== $(date -Is) starting ==" >> "$LOG_FILE"
"$PY" -m scraper.run_pipeline "$@" 2>&1 | tee -a "$LOG_FILE"
echo "== $(date -Is) finished (exit ${PIPESTATUS[0]}) ==" >> "$LOG_FILE"
