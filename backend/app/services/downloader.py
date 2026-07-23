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
ShouldPauseCallback = Callable[[], bool]


class DownloadPaused(Exception):
    """Кооперативная пауза download-job."""


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


def is_empty_names_payload(names: list[str] | None) -> bool:
    """Пустой список имён = каталог полностью отмечен скачанным (по контракту API)."""
    return names is not None and len(names) == 0


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
        should_pause: ShouldPauseCallback | None = None,
        *,
        resume: bool = False,
    ) -> str:
        """Возвращает 'completed' | 'paused' | 'failed'."""
        async with self._session_factory() as session:
            job = await session.get(DownloadJob, job_id)
            if job is None:
                return "failed"

            job.status = JobStatus.RUNNING
            if not resume or job.started_at is None:
                job.started_at = datetime.now(tz=NSK)
            job.finished_at = None
            job.message = "Продолжение скачивания" if resume else "Старт скачивания каталога"
            job.error = None
            await session.commit()
            await self._emit(session, job, on_progress)

            try:
                await self._download_all(session, job, on_progress, should_pause)
                job.status = JobStatus.COMPLETED
                job.finished_at = datetime.now(tz=NSK)
                job.message = (
                    f"Каталог скачан полностью (пустой список имён от API). "
                    f"Уникальных файлов за сессию: {job.total_downloaded}"
                )
                await session.commit()
                await self._emit(session, job, on_progress)
                return "completed"
            except DownloadPaused:
                job.status = JobStatus.PAUSED
                job.message = (
                    f"Скачивание приостановлено. Уникальных файлов за сессию: "
                    f"{job.total_downloaded}"
                )
                await session.commit()
                await self._emit(session, job, on_progress)
                return "paused"
            except Exception as exc:
                logger.exception("Download job %s failed", job_id)
                job.status = JobStatus.FAILED
                job.finished_at = datetime.now(tz=NSK)
                job.error = str(exc)
                job.message = "Ошибка скачивания"
                await session.commit()
                await self._emit(session, job, on_progress)
                return "failed"

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

    def _check_pause(self, should_pause: ShouldPauseCallback | None) -> None:
        if should_pause is not None and should_pause():
            raise DownloadPaused()

    async def _download_all(
        self,
        session: AsyncSession,
        job: DownloadJob,
        on_progress: ProgressCallback | None,
        should_pause: ShouldPauseCallback | None,
    ) -> None:
        async def on_waiting(message: str, retry_after: float, status_code: int) -> None:
            await self._on_waiting(
                session, job, on_progress, message, retry_after, status_code
            )

        while True:
            self._check_pause(should_pause)

            names = await self._client.get_file_names(on_waiting=on_waiting)
            logger.info(
                "Job %s: GET /names → %s имён (candidate=%s)",
                job.id,
                len(names),
                self._client.candidate_headers.get("X-Candidate-Id"),
            )

            if is_empty_names_payload(names):
                logger.info(
                    "Job %s: пустой file_names [] — каталог полностью скачан",
                    job.id,
                )
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
                self._check_pause(should_pause)
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

        new_files = 0
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
                        job_id=job.id,
                    )
                )
                new_files += 1
            else:
                existing.content = content
                existing.downloaded_at = datetime.now(tz=NSK)
                existing.job_id = job.id

        await session.flush()

        mark_result = await self._client.mark_downloaded(batch, on_waiting=on_waiting)
        logger.info(
            "Job %s: mark %s → marked_now=%s already_marked=%s new_local=%s",
            job.id,
            batch,
            mark_result.marked_now,
            mark_result.already_marked,
            new_files,
        )

        job.downloaded_in_batch += len(batch)
        job.total_downloaded += new_files
        job.status = JobStatus.RUNNING
        job.message = (
            f"Получено {job.names_received} названий файлов, "
            f"скачиваю / скачано {job.downloaded_in_batch} из {job.names_received}"
        )
        await session.commit()
        await self._emit(session, job, on_progress)
