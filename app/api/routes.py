from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel

from app.core.queue import enqueue_transcription
from app.services.storage import storage_service
from app.services.supabase_service import supabase_service

router = APIRouter()


class JobResponse(BaseModel):
    id: str
    original_filename: str
    audio_path: str
    status: str
    transcript: Optional[str] = None
    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    retry_count: int
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None


class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    page: int
    page_size: int


class UploadResponse(BaseModel):
    job_id: str
    status: str
    message: str


@router.post(
    "/transcriptions",
    response_model=UploadResponse,
    status_code=202,
    summary="Upload audio for transcription",
    description="Upload an audio file. Returns a job ID to poll for results.",
)
async def upload_audio(
    file: UploadFile = File(..., description="Audio file (mp3, wav, m4a, ogg, flac)"),
):
    if not supabase_service.is_configured():
        raise HTTPException(status_code=500, detail="Supabase is not configured")
    
    # Save audio
    job_id, audio_path = await storage_service.save_audio(file)

    # Create DB record in Supabase
    await supabase_service.create_job(job_id, file.filename, audio_path)

    # Enqueue for async processing
    await enqueue_transcription(job_id, audio_path)

    return UploadResponse(
        job_id=job_id,
        message="Audio uploaded successfully. Use the job_id to poll for results.",
        status="pending",
    )


@router.get(
    "/transcriptions/{job_id}",
    response_model=JobResponse,
    summary="Get transcription status and result",
)
async def get_transcription(job_id: str):
    if not supabase_service.is_configured():
        raise HTTPException(status_code=500, detail="Supabase is not configured")
    
    job = await supabase_service.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    return JobResponse(**job)


@router.get(
    "/transcriptions",
    response_model=JobListResponse,
    summary="List all transcription jobs",
)
async def list_transcriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status"),
):
    if not supabase_service.is_configured():
        raise HTTPException(status_code=500, detail="Supabase is not configured")
    
    jobs, total = await supabase_service.list_jobs(status, page, page_size)

    return JobListResponse(
        jobs=[JobResponse(**j) for j in jobs],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.delete(
    "/transcriptions/{job_id}",
    status_code=204,
    summary="Delete a transcription job",
)
async def delete_transcription(job_id: str):
    if not supabase_service.is_configured():
        raise HTTPException(status_code=500, detail="Supabase is not configured")
    
    job = await supabase_service.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job["status"] == "processing":
        raise HTTPException(
            status_code=409, detail="Cannot delete a job that is currently processing"
        )

    storage_service.delete_audio(job["audio_path"])
    await supabase_service.delete_job(job_id)
