#!/usr/bin/env bash
# Деплой на VPS: git pull + docker compose up --build
# Использование: ./scripts/deploy.sh
# Требует: scripts/deploy.env + SSH-доступ к серверу

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/deploy.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Создай ${ENV_FILE} из deploy.env.example"
  exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"

SSH_HOST="${SSH_HOST:?}"
SSH_PORT="${SSH_PORT:?}"
SSH_USER="${SSH_USER:?}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/opt/files-downloader}"
APP_HOST_PORT="${APP_HOST_PORT:-8088}"

echo "==> Deploy to ${SSH_USER}@${SSH_HOST}:${SSH_PORT} (${REMOTE_APP_DIR})"

ssh -p "${SSH_PORT}" "${SSH_USER}@${SSH_HOST}" bash -s <<EOF
set -euo pipefail
cd "${REMOTE_APP_DIR}"
git pull --ff-only
export APP_HOST_PORT="${APP_HOST_PORT}"
docker compose up -d --build
docker compose ps
echo "OK: http://${SSH_HOST}:${APP_HOST_PORT}"
EOF

echo "==> Done"
