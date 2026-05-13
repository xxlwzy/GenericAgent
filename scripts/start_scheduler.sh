#!/bin/bash
# Wrapper for GA scheduler (launchd / cron). Paths resolve from this script's location.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export PYTHONPATH="$ROOT"

cd "$ROOT"
exec python3 "$ROOT/agentmain.py" --reflect "$ROOT/reflect/scheduler.py"
