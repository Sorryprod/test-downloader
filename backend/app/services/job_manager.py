from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import DownloadJob, JobStatus
from app.schemas import JobProgress
from app.services.downloader import DownloadService, format_nsk
from app.services.external_client import ExternalFilesClient

logger = logging.getLogger(__name__)


def job_to_progress(job: DownloadJob) -> JobProgress:
    return JobProgress(
        job_id=job.id,
        status=job.status,
        started_at=job.started_at,
        started_at_nsk=format_nsk(job.started_at),
        names_received=job.names_received,
        downloaded_in_batch=job.downloaded_in_batch,
        total_downloaded=job.total_downloaded,
        message=job.message,
        error=job.error,
    )


class JobManager:
    """Хранит подписчиков SSE и запускает фоновые download-job."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        external_client: ExternalFilesClient,
    ) -> None:
        self._session_factory = session_factory
        self._download_service = DownloadService(session_factory, external_client)
        self._subscribers: dict[int, list[asyncio.Queue[JobProgress | None]]] = defaultdict(
            list
        )
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._pause_requested: set[int] = set()
        self._lock = asyncio.Lock()

    def _is_pause_requested(self, job_id: int) -> bool:
        return job_id in self._pause_requested

    async def start_job(self) -> DownloadJob:
        async with self._lock:
            running = [task for task in self._tasks.values() if not task.done()]
            if running:
                async with self._session_factory() as session:
                    result = await session.scalar(
                        select(DownloadJob)
                        .where(
                            DownloadJob.status.in_(
                                [
                                    JobStatus.PENDING,
                                    JobStatus.RUNNING,
                                    JobStatus.WAITING_RATE_LIMIT,
                                ]
                            )
                        )
                        .order_by(DownloadJob.id.desc())
                    )
                    if result is not None:
                        return result

            async with self._session_factory() as session:
                job = DownloadJob(
                    status=JobStatus.PENDING,
                    message="Ожидание запуска",
                )
                session.add(job)
                await session.commit()
                await session.refresh(job)
                job_id = job.id

            self._pause_requested.discard(job_id)
            task = asyncio.create_task(
                self._run(job_id, resume=False),
                name=f"download-job-{job_id}",
            )
            self._tasks[job_id] = task
            return job

    async def pause_job(self, job_id: int) -> DownloadJob:
        async with self._session_factory() as session:
            job = await session.get(DownloadJob, job_id)
            if job is None:
                raise KeyError("job_not_found")
            if job.status not in (
                JobStatus.PENDING,
                JobStatus.RUNNING,
                JobStatus.WAITING_RATE_LIMIT,
            ):
                raise ValueError(f"Нельзя поставить на паузу статус {job.status}")

        self._pause_requested.add(job_id)
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            # Ждём кооперативной остановки (с таймаутом на случай долгого Retry-After)
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        async with self._session_factory() as session:
            job = await session.get(DownloadJob, job_id)
            if job is None:
                raise KeyError("job_not_found")
            if job.status != JobStatus.PAUSED:
                # Если ещё в rate-limit sleep — пометим paused после выхода; иначе форсим
                if job.status in (
                    JobStatus.RUNNING,
                    JobStatus.WAITING_RATE_LIMIT,
                    JobStatus.PENDING,
                ):
                    job.status = JobStatus.PAUSED
                    job.message = "Скачивание приостановлено"
                    await session.commit()
                    await self.publish(job)
            return job

    async def resume_job(self, job_id: int) -> DownloadJob:
        async with self._lock:
            async with self._session_factory() as session:
                job = await session.get(DownloadJob, job_id)
                if job is None:
                    raise KeyError("job_not_found")
                if job.status != JobStatus.PAUSED:
                    raise ValueError(f"Продолжить можно только paused, сейчас {job.status}")

            existing = self._tasks.get(job_id)
            if existing is not None and not existing.done():
                return job

            self._pause_requested.discard(job_id)
            task = asyncio.create_task(
                self._run(job_id, resume=True),
                name=f"download-job-{job_id}-resume",
            )
            self._tasks[job_id] = task

            async with self._session_factory() as session:
                job = await session.get(DownloadJob, job_id)
                assert job is not None
                return job

    async def _run(self, job_id: int, *, resume: bool) -> None:
        try:
            await self._download_service.run_job(
                job_id,
                on_progress=self.publish,
                should_pause=lambda: self._is_pause_requested(job_id),
                resume=resume,
            )
        finally:
            self._pause_requested.discard(job_id)
            await self.publish_terminal(job_id)

    async def publish(self, job: DownloadJob) -> None:
        progress = job_to_progress(job)
        for queue in list(self._subscribers.get(job.id, [])):
            await queue.put(progress)

    async def publish_terminal(self, job_id: int) -> None:
        for queue in list(self._subscribers.get(job_id, [])):
            await queue.put(None)

    def subscribe(self, job_id: int) -> asyncio.Queue[JobProgress | None]:
        queue: asyncio.Queue[JobProgress | None] = asyncio.Queue(maxsize=64)
        self._subscribers[job_id].append(queue)
        return queue

    def unsubscribe(self, job_id: int, queue: asyncio.Queue[JobProgress | None]) -> None:
        subscribers = self._subscribers.get(job_id, [])
        if queue in subscribers:
            subscribers.remove(queue)

    async def event_stream(self, job_id: int) -> AsyncIterator[JobProgress]:
        async with self._session_factory() as session:
            job = await session.get(DownloadJob, job_id)
            if job is None:
                return
            yield job_to_progress(job)
            if job.status in (
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.PAUSED,
            ):
                return

        queue = self.subscribe(job_id)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    async with self._session_factory() as session:
                        job = await session.get(DownloadJob, job_id)
                        if job is not None:
                            yield job_to_progress(job)
                    break
                yield item
        finally:
            self.unsubscribe(job_id, queue)
