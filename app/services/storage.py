import uuid
import shutil
from pathlib import Path

from fastapi import UploadFile, HTTPException

from app.core.config import settings


class StorageService:
    def __init__(self):
        settings.AUDIO_PATH.mkdir(parents=True, exist_ok=True)
        settings.TRANSCRIPT_PATH.mkdir(parents=True, exist_ok=True)

    def _validate_file(self, file: UploadFile) -> None:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '.{ext}'. Allowed: {settings.ALLOWED_EXTENSIONS}",
            )

    async def save_audio(self, file: UploadFile) -> tuple[str, str]:
        """Save uploaded audio file. Returns (job_id, file_path)."""
        self._validate_file(file)

        job_id = str(uuid.uuid4())
        ext = file.filename.rsplit(".", 1)[-1].lower()
        filename = f"{job_id}.{ext}"
        dest = settings.AUDIO_PATH / filename

        # Stream to disk to avoid loading entire file in memory
        with open(dest, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                size_mb = dest.stat().st_size / (1024 * 1024) if dest.exists() else 0
                if size_mb > settings.MAX_FILE_SIZE_MB:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Max size: {settings.MAX_FILE_SIZE_MB}MB",
                    )
                f.write(chunk)

        return job_id, str(dest)

    def save_transcript(self, job_id: str, text: str) -> str:
        """Save transcript text to file. Returns file path."""
        dest = settings.TRANSCRIPT_PATH / f"{job_id}.txt"
        dest.write_text(text, encoding="utf-8")
        return str(dest)

    def delete_audio(self, audio_path: str) -> None:
        Path(audio_path).unlink(missing_ok=True)


storage_service = StorageService()
