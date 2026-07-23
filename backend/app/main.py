import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import get_settings
from app.core.db import init_db
from app.services.external_client import ExternalFilesClient
from app.services.job_manager import JobManager
from app.core.db import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()

    external_client = ExternalFilesClient(settings)
    job_manager = JobManager(AsyncSessionLocal, external_client)
    app.state.settings = settings
    app.state.external_client = external_client
    app.state.job_manager = job_manager

    yield

    await external_client.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Files Downloader & Analyzer",
        description="Сервис скачивания и анализа файлов (тестовое задание)",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
