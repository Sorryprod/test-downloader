from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo
from zipfile import ZipFile

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import DownloadJob, DownloadedFile, JobStatus
from app.services.external_client import ExternalApiError, ExternalFilesClient

logger = logging.getLogger(__name__)

NSK = ZoneInfo("Asia/Novosibirsk")

ProgressCallback = Callable[[DownloadJob], Awaitable[None]]


def format_nsk(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    local = dt.astimezone(NSK)
    return local.strftime("%d.%m.%Y %H:%M:%S НСК")


def extract_text_files_from_zip(zip_bytes: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    with ZipFile(BytesIO(zip_bytes)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.split("/")[-1]
            raw = archive.read(info)
            result[name] = raw.decode("utf-8")
    return result


class DownloadService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        external_client: ExternalFilesClient,
    ) -> None:
        self._session_factory = session_factory
        self._client = external_client

    async def run_job(
        self,
        job_id: int,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        async with self._session_factory() as session:
            job = await session.get(DownloadJob, job_id)
            if job is None:
                return

            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(tz=NSK)
            job.message = "Старт скачивания каталога"
            job.error = None
            await session.commit()
            await self._emit(session, job, on_progress)

            try:
                await self._download_all(session, job, on_progress)
                job.status = JobStatus.COMPLETED
                job.finished_at = datetime.now(tz=NSK)
                job.message = (
                    f"Каталог скачан полностью. Всего файлов: {job.total_downloaded}"
                )
                await session.commit()
                await self._emit(session, job, on_progress)
            except Exception as exc:
                logger.exception("Download job %s failed", job_id)
                job.status = JobStatus.FAILED
                job.finished_at = datetime.now(tz=NSK)
                job.error = str(exc)
                job.message = "Ошибка скачивания"
                await session.commit()
                await self._emit(session, job, on_progress)

    async def _emit(
        self,
        session: AsyncSession,
        job: DownloadJob,
        on_progress: ProgressCallback | None,
    ) -> None:
        await session.refresh(job)
        if on_progress is not None:
            await on_progress(job)

    async def _on_waiting(
        self,
        session: AsyncSession,
        job: DownloadJob,
        on_progress: ProgressCallback | None,
        message: str,
        retry_after: float,
        status_code: int,
    ) -> None:
        job.status = JobStatus.WAITING_RATE_LIMIT
        job.message = message
        await session.commit()
        await self._emit(session, job, on_progress)
        # Фактический sleep делает клиент; здесь только статус для UI

    async def _download_all(
        self,
        session: AsyncSession,
        job: DownloadJob,
        on_progress: ProgressCallback | None,
    ) -> None:
        async def on_waiting(message: str, retry_after: float, status_code: int) -> None:
            await self._on_waiting(
                session, job, on_progress, message, retry_after, status_code
            )

        while True:
            names = await self._client.get_file_names(on_waiting=on_waiting)
            if not names:
                job.names_received = 0
                job.downloaded_in_batch = 0
                if job.status == JobStatus.WAITING_RATE_LIMIT:
                    job.status = JobStatus.RUNNING
                job.message = "Внешний API вернул пустой список имён — каталог скачан"
                await session.commit()
                await self._emit(session, job, on_progress)
                return

            job.status = JobStatus.RUNNING
            job.names_received = len(names)
            job.downloaded_in_batch = 0
            job.message = (
                f"Получено {job.names_received} названий файлов, "
                f"скачиваю / скачано {job.downloaded_in_batch} из {job.names_received}"
            )
            await session.commit()
            await self._emit(session, job, on_progress)

            for offset in range(0, len(names), 3):
                batch = names[offset : offset + 3]
                await self._download_and_mark_batch(
                    session, job, batch, on_progress, on_waiting
                )

    async def _download_and_mark_batch(
        self,
        session: AsyncSession,
        job: DownloadJob,
        batch: list[str],
        on_progress: ProgressCallback | None,
        on_waiting,
    ) -> None:
        zip_bytes = await self._client.download_files(batch, on_waiting=on_waiting)
        extracted = extract_text_files_from_zip(zip_bytes)

        missing = [name for name in batch if name not in extracted]
        if missing:
            raise ExternalApiError(
                f"В ZIP отсутствуют файлы: {', '.join(missing)}",
                status_code=None,
            )

        saved_names: list[str] = []
        for filename in batch:
            content = extracted[filename]
            existing = await session.scalar(
                select(DownloadedFile).where(DownloadedFile.filename == filename)
            )
            if existing is None:
                session.add(
                    DownloadedFile(
                        filename=filename,
                        content=content,
                        downloaded_at=datetime.now(tz=NSK),
                    )
                )
            else:
                existing.content = content
                existing.downloaded_at = datetime.now(tz=NSK)
            saved_names.append(filename)

        await session.flush()

        # Mark после успешного сохранения — строгий порядок из ТЗ
        await self._client.mark_downloaded(saved_names, on_waiting=on_waiting)

        job.downloaded_in_batch += len(saved_names)
        job.total_downloaded += len(saved_names)
        job.status = JobStatus.RUNNING
        job.message = (
            f"Получено {job.names_received} названий файлов, "
            f"скачиваю / скачано {job.downloaded_in_batch} из {job.names_received}"
        )
        await session.commit()
        await self._emit(session, job, on_progress)
