#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

setup_log "smoke-ha"

cd "$ROOT_DIR"

run "sudo docker compose -f docker-compose.ha.yml up -d --build"
run "sleep 5"
run "sudo docker compose -f docker-compose.ha.yml ps"

assert_http_code "http://localhost:8081/ready" "200" "/tmp/anon_ha_ready.txt"
cat /tmp/anon_ha_ready.txt
assert_http_code "http://localhost:8404/stats" "200" "/tmp/anon_ha_stats.html"

echo "[STEP] Testing upload through HAProxy"
curl -s -F "file=@$ROOT_DIR/ejemplo.docx" "http://localhost:8081/upload" > /tmp/anon_test_upload.json
assert_json_upload_shape "/tmp/anon_test_upload.json"

echo "[STEP] Testing export through HAProxy"
assert_export_docx_ok "/tmp/anon_test_upload.json" "http://localhost:8081"

run "sudo docker compose -f docker-compose.ha.yml stop web1 web2 web3 web4 web5"
run "sleep 3"
assert_http_code "http://localhost:8081/" "503" "/tmp/anon_test_503.html"
assert_file_contains "/tmp/anon_test_503.html" "En espera de Anonimizador"
assert_file_contains "/tmp/anon_test_503.html" "content=\"10\""

run "sudo docker compose -f docker-compose.ha.yml start web1 web2 web3 web4 web5"
run "sleep 15"
assert_http_code "http://localhost:8081/ready" "200" "/tmp/anon_test_ready_after.txt"
cat /tmp/anon_test_ready_after.txt

echo ""
echo "[OK] Smoke HA test finished successfully: $(date -Iseconds)"
echo "[OK] Log: $LOG_FILE"
