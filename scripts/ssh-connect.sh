#!/usr/bin/env bash
# Подключение к VPS по SSH.
# Использование: ./scripts/ssh-connect.sh
# Требует: scripts/deploy.env (см. deploy.env.example)

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

exec ssh -p "${SSH_PORT}" "${SSH_USER}@${SSH_HOST}" "$@"
