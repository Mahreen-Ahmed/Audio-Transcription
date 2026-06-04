from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # App
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/transcription_db"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Storage
    STORAGE_PATH: Path = Path("/app/storage")
    AUDIO_PATH: Path = Path("/app/storage/audio")
    TRANSCRIPT_PATH: Path = Path("/app/storage/transcripts")

    # Whisper
    WHISPER_MODEL: str = "base"  # tiny, base, small, medium, large

    # Upload limits
    MAX_FILE_SIZE_MB: int = 100
    ALLOWED_EXTENSIONS: list[str] = ["mp3", "wav", "m4a", "ogg", "flac", "mp4", "webm"]

    # Worker
    MAX_RETRIES: int = 3
    RETRY_DELAYS: list[int] = [30, 120, 600]  # seconds
    
    # Supabase
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()
