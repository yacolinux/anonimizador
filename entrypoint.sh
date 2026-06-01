#!/bin/bash
set -e

OPENCODE_CONFIG_DIR="${HOME}/.config/opencode"
OPENCODE_DATA_DIR="${HOME}/.local/share/opencode"
APP_ENV_FILE="/app/.env"
APP_ENV_EXAMPLE_FILE="/app/.env.example"

mkdir -p "${OPENCODE_CONFIG_DIR}"
mkdir -p "${OPENCODE_DATA_DIR}"

if [ ! -f "${APP_ENV_FILE}" ]; then
  if [ -f "${APP_ENV_EXAMPLE_FILE}" ]; then
    cp "${APP_ENV_EXAMPLE_FILE}" "${APP_ENV_FILE}"
  else
    echo "No se encontró ${APP_ENV_EXAMPLE_FILE}" >&2
    exit 1
  fi
fi

set -a
. "${APP_ENV_FILE}"
set +a

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
