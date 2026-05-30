#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[RUN_ALL] Starting full smoke suite"
echo "[RUN_ALL] $(date -Iseconds)"

"$SCRIPT_DIR/smoke_single.sh"
"$SCRIPT_DIR/smoke_ha.sh"

echo "[RUN_ALL] Suite completed successfully"
echo "[RUN_ALL] $(date -Iseconds)"
