import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.core.queue import redis_settings, enqueue_transcription
from app.models.job import TranscriptionJob, JobStatus
from app.services.transcriber import transcribe_audio
from app.services.storage import storage_service


async def process_transcription(ctx, *, job_id: str, audio_path: str, retry: int = 0):
    """
    Main worker function: picks up a transcription job, runs Whisper,
    updates the DB, and handles retries on failure.
    """
    print(f"[Worker] Processing job {job_id} (attempt {retry + 1})")

    async with AsyncSessionLocal() as session:
        # Fetch job
        result = await session.execute(
            select(TranscriptionJob).where(TranscriptionJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            print(f"[Worker] Job {job_id} not found, skipping")
            return

        # Mark as processing
        job.status = JobStatus.PROCESSING
        job.updated_at = datetime.now(timezone.utc)
        await session.commit()

    try:
        # Run transcription (blocking CPU call — run in thread pool)
        loop = asyncio.get_event_loop()
        transcription = await loop.run_in_executor(None, transcribe_audio, audio_path)

        # Save transcript file
        storage_service.save_transcript(job_id, transcription["text"])

        # Update job as completed
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TranscriptionJob).where(TranscriptionJob.id == job_id)
            )
            job = result.scalar_one()
            job.status = JobStatus.COMPLETED
            job.transcript = transcription["text"]
            job.language = transcription["language"]
            job.duration_seconds = transcription["duration_seconds"]
            job.completed_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            await session.commit()

        print(f"[Worker] Job {job_id} completed successfully")

    except Exception as exc:
        print(f"[Worker] Job {job_id} failed: {exc}")
        await _handle_failure(job_id, audio_path, str(exc), retry)


async def _handle_failure(job_id: str, audio_path: str, error: str, retry: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TranscriptionJob).where(TranscriptionJob.id == job_id)
        )
        job = result.scalar_one()
        job.retry_count = retry + 1
        job.error_message = error
        job.updated_at = datetime.now(timezone.utc)

        if retry < settings.MAX_RETRIES - 1:
            # Schedule retry with exponential backoff
            delay = settings.RETRY_DELAYS[retry]
            print(f"[Worker] Scheduling retry {retry + 1} for job {job_id} in {delay}s")
            job.status = JobStatus.PENDING
            await session.commit()
            await enqueue_transcription(job_id, audio_path, retry=retry + 1)
        else:
            # Max retries exceeded — move to dead letter
            print(f"[Worker] Job {job_id} exceeded max retries, marking as failed")
            job.status = JobStatus.FAILED
            await session.commit()


async def startup(ctx):
    await init_db()
    print("[Worker] Started and ready")


async def shutdown(ctx):
    print("[Worker] Shutting down")


class WorkerSettings:
    functions = [process_transcription]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings
    max_jobs = 5  # concurrent workers
    job_timeout = 600  # 10 min max per job
    keep_result = 3600  # keep result for 1 hour
