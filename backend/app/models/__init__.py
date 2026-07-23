from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_RATE_LIMIT = "waiting_rate_limit"
    COMPLETED = "completed"
    FAILED = "failed"


class DownloadedFile(Base):
    __tablename__ = "downloaded_files"
    __table_args__ = (UniqueConstraint("filename", name="uq_downloaded_files_filename"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )


class DownloadJob(Base):
    __tablename__ = "download_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default=JobStatus.PENDING)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Текущая порция имён с внешнего API
    names_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    downloaded_in_batch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Накопительный счётчик успешно сохранённых файлов за этот job
    total_downloaded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
