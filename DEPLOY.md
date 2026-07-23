# Деплой на VPS

Доступ по **SSH логин/пароль**. Хост, порт и пароль — только в GitHub Secrets и локальном `scripts/deploy.env` (gitignore).

Каталог на сервере: `/root/test-downloader`  
HTTP-порт: `APP_HOST_PORT` (по умолчанию `8088`)

## CI/CD

- **CI** — `.github/workflows/ci.yml`
- **CD** — `.github/workflows/deploy.yml` (password auth через `SSH_PASSWORD`)

---

## GitHub Secrets

| Secret | Описание |
|--------|----------|
| `SSH_HOST` | IP VPS |
| `SSH_PORT` | SSH-порт |
| `SSH_USER` | `root` |
| `SSH_PASSWORD` | пароль root |
| `REMOTE_APP_DIR` | `/root/test-downloader` |
| `APP_HOST_PORT` | `8088` (опционально) |
| `GIT_REPO_URL` | `https://github.com/Sorryprod/test-downloader.git` (опционально) |

После заполнения Secrets: Actions → **Deploy** → Run workflow (или просто push в `main`).

---

## Локальный деплой

```powershell
copy scripts\deploy.env.example scripts\deploy.env
# заполни SSH_HOST, SSH_PORT, SSH_USER, SSH_PASSWORD

backend\.venv\Scripts\pip install paramiko
backend\.venv\Scripts\python scripts\deploy_remote.py
```

На сервере в `/root/test-downloader/.env` после первого деплоя проверь:

- `X_CANDIDATE_ID`
- `EXTERNAL_API_BASE_URL`
- `CORS_ORIGINS` (твой `http://IP:8088`)

---

## Первый запуск на сервере вручную (если нужно)

```bash
cd /root/test-downloader
git clone https://github.com/Sorryprod/test-downloader.git .
cp .env.example .env && nano .env
export APP_HOST_PORT=8088
docker compose up -d --build
ufw allow 8088/tcp   # если используешь ufw
```
