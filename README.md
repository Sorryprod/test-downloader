# Files Downloader & Analyzer

Сервис со своим UI: скачивает каталог текстовых файлов через внешнее API и считает статистику по цифрам.

**Candidate-Id:** задаётся в `.env` (`X_CANDIDATE_ID`)  
**External API:** задаётся в `.env` (`EXTERNAL_API_BASE_URL`)  
**Demo URL:** не публикуется в репозитории — смотри GitHub Secret `DEMO_URL` / сопроводительное письмо

## Быстрый старт (Docker)

```bash
cp .env.example .env
# заполни X_CANDIDATE_ID и EXTERNAL_API_BASE_URL
docker compose up --build
```

Откройте http://localhost:8088 (порт задаётся `APP_HOST_PORT`).

## Локальная разработка

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

UI: http://localhost:5173 (прокси `/api` → backend).

### Тесты

```bash
cd backend
pytest
```

## CI/CD

- **CI** — GitHub Actions: pytest + сборка frontend (`.github/workflows/ci.yml`)
- **CD** — деплой по SSH на VPS после push в `main` (`.github/workflows/deploy.yml`)

Хост, SSH-порт и пароль хранятся только в **GitHub Secrets** (`SSH_PASSWORD`) и локальном `scripts/deploy.env` (gitignore).

Инструкция: **[DEPLOY.md](DEPLOY.md)**

```powershell
# заполни SSH_PASSWORD в scripts\deploy.env
backend\.venv\Scripts\python scripts\deploy_remote.py
```

## Что сделано по ТЗ

1. **Скачивание** — кнопка «Скачать данные» в шапке на любой странице.
2. Цикл `names → download(≤3) → mark downloaded` до пустого списка имён.
3. Прогресс: время старта **НСК**, «получено N / скачано M из N», статус rate-limit.
4. Список файлов с сортировкой по времени, пагинацией и выбором (точечно / страница / все).
5. Расчёты: overall + per-file частоты цифр `0–9`.

## Архитектурные решения

- **FastAPI + asyncio + httpx** — асинхронный клиент с паузами и уважением к `Retry-After` при `429`/`403`.
- **SQLAlchemy 2.0 + PostgreSQL** — хранение файлов и job-статусов.
- **SSE** — поток прогресса download-job без WebSocket.
- **Идемпотентность** — уникальность имени файла; mark только после успешного сохранения.
- **React + TypeScript** — простое SPA на две страницы.
- **Docker Compose** — app + Postgres + nginx; HTTP-порт хоста через `APP_HOST_PORT`.

## API нашего сервиса

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/jobs/download` | Старт скачивания |
| GET | `/api/jobs/{id}` | Статус job |
| GET | `/api/jobs/{id}/events` | SSE прогресс |
| GET | `/api/files` | Список файлов (`page`, `page_size`) |
| POST | `/api/files/calculate` | Расчёты (`file_ids` или `select_all`) |
| GET | `/api/health` | Healthcheck |
