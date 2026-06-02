#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/testing/logs"

setup_log() {
  local prefix="$1"
  local ts
  ts="$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$LOG_DIR"
  LOG_FILE="$LOG_DIR/${prefix}-${ts}.log"
  export LOG_FILE
  exec > >(tee -a "$LOG_FILE") 2>&1
  echo "[INFO] Test started: $(date -Iseconds)"
  echo "[INFO] Log file: $LOG_FILE"
}

run() {
  echo ""
  echo "[STEP] $*"
  eval "$*"
}

assert_http_code() {
  local url="$1"
  local expected="$2"
  local out_file="${3:-/tmp/anon_test_body.txt}"
  local code
  code="$(curl -s -o "$out_file" -w "%{http_code}" "$url")"
  echo "[CHECK] $url -> HTTP $code"
  if [[ "$code" != "$expected" ]]; then
    echo "[ERROR] Expected HTTP $expected, got $code"
    cat "$out_file" || true
    exit 1
  fi
}

assert_file_contains() {
  local file_path="$1"
  local needle="$2"
  python3 - <<PY
from pathlib import Path
content = Path('$file_path').read_text(errors='ignore')
assert '$needle' in content, 'missing text: $needle'
print('[CHECK] found in file:', '$needle')
PY
}

assert_json_upload_shape() {
  local file_path="$1"
  python3 - <<PY
import json
obj = json.load(open('$file_path'))
print('[CHECK] upload keys:', sorted(obj.keys()))
assert obj.get('filename'), 'missing filename'
assert isinstance(obj.get('positions'), list), 'positions must be list'
assert obj.get('ai_status') in ('ok', 'busy', 'unavailable', 'timeout', 'error', 'disabled', 'skipped'), 'invalid ai_status'
assert obj.get('analysis_mode') in ('full', 'regex_only'), 'invalid analysis_mode'
print('[CHECK] upload response OK')
PY
}

assert_export_docx_ok() {
  local upload_json_path="$1"
  local base_url="$2"
  python3 - <<PY
import json
import requests
upload = json.load(open('$upload_json_path'))
kw = [{'word': p['word'], 'type': p.get('type', 'other')} for p in upload.get('positions', [])]
payload = {
    'filename': upload['filename'],
    'keywords': kw,
    'format': 'docx',
    'replacement': '[REDACTADO]'
}
res = requests.post('$base_url/export', json=payload, timeout=180)
print('[CHECK] export status:', res.status_code)
assert res.status_code == 200, f'export failed: {res.text[:200]}'
print('[CHECK] export content-type:', res.headers.get('Content-Type'))
PY
}
