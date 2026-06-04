from datetime import datetime
from pydantic import BaseModel

from app.models.job import JobStatus


class JobResponse(BaseModel):
    id: str
    original_filename: str
    status: JobStatus
    transcript: str | None = None
    language: str | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    retry_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    page: int
    page_size: int


class UploadResponse(BaseModel):
    job_id: str
    message: str
    status: JobStatus
