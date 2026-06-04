from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.queue import enqueue_transcription
from app.models.job import TranscriptionJob, JobStatus
from app.models.schemas import JobResponse, JobListResponse, UploadResponse
from app.services.storage import storage_service

router = APIRouter()


@router.post(
    "/transcriptions",
    response_model=UploadResponse,
    status_code=202,
    summary="Upload audio for transcription",
    description="Upload an audio file. Returns a job ID to poll for results.",
)
async def upload_audio(
    file: UploadFile = File(..., description="Audio file (mp3, wav, m4a, ogg, flac)"),
    db: AsyncSession = Depends(get_db),
):
    # Save audio to disk
    job_id, audio_path = await storage_service.save_audio(file)

    # Create DB record
    job = TranscriptionJob(
        id=job_id,
        original_filename=file.filename,
        audio_path=audio_path,
        status=JobStatus.PENDING,
    )
    db.add(job)
    await db.commit()

    # Enqueue for async processing
    await enqueue_transcription(job_id, audio_path)

    return UploadResponse(
        job_id=job_id,
        message="Audio uploaded successfully. Use the job_id to poll for results.",
        status=JobStatus.PENDING,
    )


@router.get(
    "/transcriptions/{job_id}",
    response_model=JobResponse,
    summary="Get transcription status and result",
)
async def get_transcription(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TranscriptionJob).where(TranscriptionJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    return JobResponse.model_validate(job)


@router.get(
    "/transcriptions",
    response_model=JobListResponse,
    summary="List all transcription jobs",
)
async def list_transcriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: JobStatus | None = Query(None, description="Filter by status"),
    db: AsyncSession = Depends(get_db),
):
    query = select(TranscriptionJob)
    count_query = select(func.count(TranscriptionJob.id))

    if status:
        query = query.where(TranscriptionJob.status == status)
        count_query = count_query.where(TranscriptionJob.status == status)

    total = (await db.execute(count_query)).scalar()

    query = (
        query.order_by(TranscriptionJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    jobs = (await db.execute(query)).scalars().all()

    return JobListResponse(
        jobs=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete(
    "/transcriptions/{job_id}",
    status_code=204,
    summary="Delete a transcription job",
)
async def delete_transcription(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TranscriptionJob).where(TranscriptionJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job.status == JobStatus.PROCESSING:
        raise HTTPException(
            status_code=409, detail="Cannot delete a job that is currently processing"
        )

    storage_service.delete_audio(job.audio_path)
    await db.delete(job)
    await db.commit()
