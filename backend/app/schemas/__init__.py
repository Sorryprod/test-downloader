from datetime import datetime

from pydantic import BaseModel, Field


class JobProgress(BaseModel):
    job_id: int
    status: str
    started_at: datetime | None = None
    started_at_nsk: str | None = None
    names_received: int = 0
    downloaded_in_batch: int = 0
    total_downloaded: int = 0
    message: str = ""
    error: str | None = None


class JobCreateResponse(BaseModel):
    job_id: int
    status: str


class FileItem(BaseModel):
    id: int
    filename: str
    downloaded_at: datetime


class FileListResponse(BaseModel):
    items: list[FileItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class CalculateRequest(BaseModel):
    file_ids: list[int] = Field(default_factory=list)
    select_all: bool = False


class FileDigitStats(BaseModel):
    file_id: int
    filename: str
    counts: dict[str, int]


class CalculateResponse(BaseModel):
    overall: dict[str, int]
    per_file: list[FileDigitStats]
    files_processed: int
