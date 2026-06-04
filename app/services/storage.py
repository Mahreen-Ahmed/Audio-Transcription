import uuid
from pathlib import Path
import io

from fastapi import UploadFile, HTTPException

from app.core.config import settings
from app.services.supabase_service import supabase_service


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
        """Save uploaded audio file. Returns (job_id, file_path or Supabase path)."""
        self._validate_file(file)

        job_id = str(uuid.uuid4())
        ext = file.filename.rsplit(".", 1)[-1].lower()
        filename = f"{job_id}.{ext}"
        
        # First read the file content to support both storage options
        file_content = await file.read()
        
        # Check file size
        size_mb = len(file_content) / (1024 * 1024)
        if size_mb > settings.MAX_FILE_SIZE_MB:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max size: {settings.MAX_FILE_SIZE_MB}MB",
            )
        
        # Try Supabase first if configured
        if supabase_service.is_configured():
            try:
                client = supabase_service.get_service_client()
                if client:
                    # Upload to Supabase Storage
                    bucket_name = "audio-files"
                    file_path = f"{filename}"
                    
                    client.storage.from_(bucket_name).upload(
                        path=file_path,
                        file=file_content,
                        file_options={"content-type": file.content_type or "audio/mpeg"}
                    )
                    
                    # Return Supabase path as "supabase://<bucket>/<path>"
                    return job_id, f"supabase://{bucket_name}/{file_path}"
            except Exception as e:
                print(f"Failed to upload to Supabase Storage: {e}. Falling back to local storage.")
        
        # Fallback to local storage
        dest = settings.AUDIO_PATH / filename
        with open(dest, "wb") as f:
            f.write(file_content)
        
        return job_id, str(dest)

    async def get_audio(self, audio_path: str) -> bytes:
        """Get audio file content from either local or Supabase storage."""
        if audio_path.startswith("supabase://"):
            # Parse Supabase path
            parts = audio_path.replace("supabase://", "").split("/", 1)
            bucket_name = parts[0]
            file_path = parts[1]
            
            client = supabase_service.get_service_client()
            if client:
                response = client.storage.from_(bucket_name).download(file_path)
                return response
        
        # Local file
        return Path(audio_path).read_bytes()

    def save_transcript(self, job_id: str, text: str) -> str:
        """Save transcript text. Returns file path or Supabase path."""
        filename = f"{job_id}.txt"
        
        # Try Supabase first if configured
        if supabase_service.is_configured():
            try:
                client = supabase_service.get_service_client()
                if client:
                    bucket_name = "transcripts"
                    file_path = f"{filename}"
                    
                    client.storage.from_(bucket_name).upload(
                        path=file_path,
                        file=text.encode("utf-8"),
                        file_options={"content-type": "text/plain"}
                    )
                    
                    return f"supabase://{bucket_name}/{file_path}"
            except Exception as e:
                print(f"Failed to upload transcript to Supabase Storage: {e}. Falling back to local storage.")
        
        # Fallback to local storage
        dest = settings.TRANSCRIPT_PATH / filename
        dest.write_text(text, encoding="utf-8")
        return str(dest)

    def delete_audio(self, audio_path: str) -> None:
        """Delete audio file from either local or Supabase storage."""
        if audio_path.startswith("supabase://"):
            # Parse Supabase path
            parts = audio_path.replace("supabase://", "").split("/", 1)
            bucket_name = parts[0]
            file_path = parts[1]
            
            try:
                client = supabase_service.get_service_client()
                if client:
                    client.storage.from_(bucket_name).remove([file_path])
            except Exception as e:
                print(f"Failed to delete from Supabase Storage: {e}")
        else:
            # Local file
            Path(audio_path).unlink(missing_ok=True)


storage_service = StorageService()
