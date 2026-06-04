import asyncio

from app.core.config import settings
from app.core.queue import redis_settings, enqueue_transcription
from app.services.transcriber import transcribe_audio
from app.services.storage import storage_service
from app.services.database_service import database_service


async def process_transcription(ctx, *, job_id: str, audio_path: str, retry: int = 0):
    """
    Main worker function: picks up a transcription job, runs Whisper,
    updates database, and handles retries on failure.
    """
    print(f"[Worker] Processing job {job_id} (attempt {retry + 1})")

    # Fetch job
    job = await database_service.get_job(job_id)

    if not job:
        print(f"[Worker] Job {job_id} not found, skipping")
        return

    # Mark as processing
    await database_service.update_job_status(job_id, "processing")

    try:
        # Run transcription (blocking CPU call — run in thread pool)
        loop = asyncio.get_event_loop()
        transcription = await loop.run_in_executor(None, transcribe_audio, audio_path)

        # Save transcript file
        storage_service.save_transcript(job_id, transcription["text"])

        # Update job as completed
        await database_service.update_job_status(
            job_id,
            "completed",
            transcript=transcription["text"],
            language=transcription["language"],
            duration_seconds=transcription["duration_seconds"]
        )

        print(f"[Worker] Job {job_id} completed successfully")

    except Exception as exc:
        print(f"[Worker] Job {job_id} failed: {exc}")
        await _handle_failure(job_id, audio_path, str(exc), retry)


async def _handle_failure(job_id: str, audio_path: str, error: str, retry: int):
    await database_service.update_job_status(
        job_id,
        "pending" if retry < settings.MAX_RETRIES - 1 else "failed",
        error_message=error,
        retry_count=retry + 1
    )

    if retry < settings.MAX_RETRIES - 1:
        # Schedule retry with exponential backoff
        delay = settings.RETRY_DELAYS[retry]
        print(f"[Worker] Scheduling retry {retry + 1} for job {job_id} in {delay}s")
        await enqueue_transcription(job_id, audio_path, retry=retry + 1)
    else:
        # Max retries exceeded
        print(f"[Worker] Job {job_id} exceeded max retries, marking as failed")


async def startup(ctx):
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
