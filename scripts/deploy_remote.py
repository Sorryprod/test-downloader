"""
Деплой на VPS по SSH (логин/пароль) через paramiko.

  backend\\.venv\\Scripts\\python scripts\\deploy_remote.py

Пароль: scripts/deploy.env → SSH_PASSWORD
либо переменная окружения SSH_PASSWORD.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("Установи paramiko: pip install paramiko")
    sys.exit(1)


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = Path(__file__).resolve().parent / "deploy.env"


def load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def main() -> int:
    file_env = load_env(ENV_FILE)
    host = os.getenv("SSH_HOST", file_env.get("SSH_HOST", ""))
    port = int(os.getenv("SSH_PORT", file_env.get("SSH_PORT", "22")))
    user = os.getenv("SSH_USER", file_env.get("SSH_USER", "root"))
    password = os.getenv("SSH_PASSWORD", file_env.get("SSH_PASSWORD", ""))
    app_dir = os.getenv(
        "REMOTE_APP_DIR", file_env.get("REMOTE_APP_DIR", "/root/test-downloader")
    )
    app_port = os.getenv("APP_HOST_PORT", file_env.get("APP_HOST_PORT", "8088"))
    repo_url = os.getenv(
        "GIT_REPO_URL",
        file_env.get(
            "GIT_REPO_URL", "https://github.com/Sorryprod/test-downloader.git"
        ),
    )

    if not host or not user:
        print("Нужны SSH_HOST и SSH_USER в scripts/deploy.env")
        return 1
    if not password:
        print("Укажи SSH_PASSWORD в scripts/deploy.env или в окружении")
        return 1

    remote_script = f"""
set -euo pipefail
APP_DIR='{app_dir}'
APP_PORT='{app_port}'
REPO_URL='{repo_url}'

mkdir -p "$APP_DIR"
cd "$APP_DIR"

if [ ! -d .git ]; then
  if [ -z "$(ls -A "$APP_DIR" 2>/dev/null || true)" ]; then
    git clone "$REPO_URL" "$APP_DIR"
  else
    git clone "$REPO_URL" /tmp/test-downloader-clone
    cp -a /tmp/test-downloader-clone/. "$APP_DIR"/
    rm -rf /tmp/test-downloader-clone
  fi
  cd "$APP_DIR"
fi

git remote set-url origin "$REPO_URL" || true
git fetch --all
git checkout main 2>/dev/null || git checkout master 2>/dev/null || true
git reset --hard origin/main 2>/dev/null || git reset --hard origin/master

if [ ! -f .env ]; then
  cp .env.example .env
  echo "WARN: .env создан из example — отредактируй на сервере"
fi

export APP_HOST_PORT="$APP_PORT"
docker compose up -d --build
docker compose ps
echo "OK: http://$HOSTNAME:$APP_PORT (проверь APP_HOST_PORT)"
"""

    print(f"==> Deploy {user}@{host}:{port} → {app_dir}")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=user,
        password=password,
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )

    try:
        stdin, stdout, stderr = client.exec_command(remote_script, get_pty=True)
        for line in stdout:
            print(line, end="")
        err = stderr.read().decode("utf-8", errors="replace")
        if err:
            print(err, end="")
        code = stdout.channel.recv_exit_status()
        return code
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
