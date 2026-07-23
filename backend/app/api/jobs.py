import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models import DownloadJob
from app.schemas import JobCreateResponse, JobProgress
from app.services.job_manager import JobManager, job_to_progress

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def get_job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


@router.post("/download", response_model=JobCreateResponse)
async def start_download(
    job_manager: JobManager = Depends(get_job_manager),
) -> JobCreateResponse:
    job = await job_manager.start_job()
    return JobCreateResponse(job_id=job.id, status=job.status)


@router.get("/{job_id}", response_model=JobProgress)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> JobProgress:
    job = await db.get(DownloadJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job не найден")
    return job_to_progress(job)


@router.get("/{job_id}/events")
async def job_events(
    job_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    job_manager: JobManager = Depends(get_job_manager),
) -> StreamingResponse:
    job = await db.get(DownloadJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job не найден")

    async def event_generator() -> AsyncIterator[str]:
        async for progress in job_manager.event_stream(job_id):
            if await request.is_disconnected():
                break
            payload = progress.model_dump(mode="json")
            yield f"event: progress\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            if progress.status in ("completed", "failed"):
                break
            # Даем event loop обработать другие задачи
            await asyncio.sleep(0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
