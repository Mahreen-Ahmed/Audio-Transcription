import arq
from arq.connections import RedisSettings

from app.core.config import settings


redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

_redis_pool = None


async def init_queue():
    global _redis_pool
    _redis_pool = await arq.create_pool(redis_settings)


async def get_queue():
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await arq.create_pool(redis_settings)
    return _redis_pool


async def enqueue_transcription(job_id: str, audio_path: str, retry: int = 0):
    pool = await get_queue()
    await pool.enqueue_job(
        "process_transcription",
        job_id=job_id,
        audio_path=audio_path,
        retry=retry,
    )
