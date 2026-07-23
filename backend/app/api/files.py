from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models import DownloadJob, DownloadedFile
from app.schemas import (
    CalculateRequest,
    CalculateResponse,
    FileDigitStats,
    FileItem,
    FileListResponse,
)
from app.services.stats import count_digits, merge_digit_counts

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("", response_model=FileListResponse)
async def list_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    job_id: int | None = Query(None, description="Фильтр по сессии скачивания"),
    db: AsyncSession = Depends(get_db),
) -> FileListResponse:
    filters = []
    if job_id is not None:
        filters.append(DownloadedFile.job_id == job_id)

    count_stmt = select(func.count()).select_from(DownloadedFile)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = await db.scalar(count_stmt) or 0
    total_pages = max(ceil(total / page_size), 1) if total else 0

    stmt = select(DownloadedFile)
    if filters:
        stmt = stmt.where(*filters)
    stmt = (
        stmt.order_by(DownloadedFile.downloaded_at.desc(), DownloadedFile.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.scalars(stmt)).all()

    return FileListResponse(
        items=[
            FileItem(
                id=row.id,
                filename=row.filename,
                downloaded_at=row.downloaded_at,
                job_id=row.job_id,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/calculate", response_model=CalculateResponse)
async def calculate_stats(
    payload: CalculateRequest,
    db: AsyncSession = Depends(get_db),
) -> CalculateResponse:
    if payload.select_all and payload.select_session:
        raise HTTPException(
            status_code=400,
            detail="Укажите либо select_all, либо select_session",
        )

    if payload.select_all:
        rows = (await db.scalars(select(DownloadedFile).order_by(DownloadedFile.id))).all()
    elif payload.select_session:
        if payload.job_id is None:
            raise HTTPException(
                status_code=400,
                detail="Для select_session нужен job_id сессии",
            )
        job = await db.get(DownloadJob, payload.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Сессия (job) не найдена")
        rows = (
            await db.scalars(
                select(DownloadedFile)
                .where(DownloadedFile.job_id == payload.job_id)
                .order_by(DownloadedFile.id)
            )
        ).all()
    else:
        if not payload.file_ids:
            raise HTTPException(status_code=400, detail="Не выбраны файлы для расчёта")
        rows = (
            await db.scalars(
                select(DownloadedFile).where(DownloadedFile.id.in_(payload.file_ids))
            )
        ).all()
        if len(rows) != len(set(payload.file_ids)):
            raise HTTPException(status_code=404, detail="Часть выбранных файлов не найдена")

    if not rows:
        raise HTTPException(status_code=400, detail="Нет файлов для расчёта")

    per_file: list[FileDigitStats] = []
    counts_list: list[dict[str, int]] = []

    for row in rows:
        try:
            counts = count_digits(row.content)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Файл {row.filename}: {exc}",
            ) from exc

        counts_list.append(counts)
        per_file.append(
            FileDigitStats(file_id=row.id, filename=row.filename, counts=counts)
        )

    return CalculateResponse(
        overall=merge_digit_counts(counts_list),
        per_file=per_file,
        files_processed=len(rows),
    )
