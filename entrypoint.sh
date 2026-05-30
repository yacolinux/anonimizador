#!/bin/bash
set -e

OPENCODE_CONFIG_DIR="${HOME}/.config/opencode"
OPENCODE_DATA_DIR="${HOME}/.local/share/opencode"

mkdir -p "${OPENCODE_CONFIG_DIR}"
mkdir -p "${OPENCODE_DATA_DIR}"

MODEL_ID="${MODEL_NAME##*/}"

cat > "${OPENCODE_CONFIG_DIR}/opencode.json" << EOF
{
  "\$schema": "https://opencode.ai/config.json"
}
EOF

if [ -n "${OPENAI_API_KEY}" ]; then
  cat > "${OPENCODE_DATA_DIR}/auth.json" << EOF
{
  "providers": {
    "opencode": {
      "type": "api",
      "key": "${OPENAI_API_KEY}"
    }
  }
}
EOF
fi

mkdir -p /app/uploads

exec gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 180 --access-logfile - --error-logfile - app:app
