#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

setup_log "smoke-single"

cd "$ROOT_DIR"

run "sudo docker compose up -d --build"
run "sleep 5"
run "sudo docker compose ps"

assert_http_code "http://localhost:5000/ready" "200" "/tmp/anon_single_ready.txt"
cat /tmp/anon_single_ready.txt

echo "[STEP] Testing upload (single instance)"
curl -s -F "file=@$ROOT_DIR/ejemplo.docx" "http://localhost:5000/upload" > /tmp/anon_single_upload.json
assert_json_upload_shape "/tmp/anon_single_upload.json"

echo "[STEP] Testing export (single instance)"
assert_export_docx_ok "/tmp/anon_single_upload.json" "http://localhost:5000"

echo ""
echo "[OK] Smoke single test finished successfully: $(date -Iseconds)"
echo "[OK] Log: $LOG_FILE"
