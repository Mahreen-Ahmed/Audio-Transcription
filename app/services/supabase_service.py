from supabase import create_client, Client
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.core.config import settings


class SupabaseService:
    _client: Optional[Client] = None
    _service_client: Optional[Client] = None

    @classmethod
    def get_client(cls) -> Optional[Client]:
        if cls._client is None and settings.SUPABASE_URL and settings.SUPABASE_ANON_KEY:
            cls._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        return cls._client

    @classmethod
    def get_service_client(cls) -> Optional[Client]:
        if cls._service_client is None and settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
            cls._service_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        return cls._service_client

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.SUPABASE_URL and settings.SUPABASE_ANON_KEY)
    
    # Database operations
    @classmethod
    async def create_job(cls, job_id: str, original_filename: str, audio_path: str) -> Dict[str, Any]:
        client = cls.get_service_client()
        if not client:
            raise Exception("Supabase not configured")
        
        now = datetime.utcnow().isoformat()
        data = {
            "id": job_id,
            "original_filename": original_filename,
            "audio_path": audio_path,
            "status": "pending",
            "retry_count": 0,
            "created_at": now,
            "updated_at": now
        }
        
        response = client.table("transcription_jobs").insert(data).execute()
        return response.data[0]
    
    @classmethod
    async def get_job(cls, job_id: str) -> Optional[Dict[str, Any]]:
        client = cls.get_service_client()
        if not client:
            raise Exception("Supabase not configured")
        
        response = client.table("transcription_jobs").select("*").eq("id", job_id).execute()
        return response.data[0] if response.data else None
    
    @classmethod
    async def list_jobs(cls, status: Optional[str] = None, page: int = 1, page_size: int = 10) -> tuple[List[Dict[str, Any]], int]:
        client = cls.get_service_client()
        if not client:
            raise Exception("Supabase not configured")
        
        query = client.table("transcription_jobs").select("*", count="exact")
        
        if status:
            query = query.eq("status", status)
        
        offset = (page - 1) * page_size
        response = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
        
        return response.data, response.count
    
    @classmethod
    async def update_job_status(cls, job_id: str, status: str, **kwargs) -> Dict[str, Any]:
        client = cls.get_service_client()
        if not client:
            raise Exception("Supabase not configured")
        
        update_data = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
            **kwargs
        }
        
        if status == "completed":
            update_data["completed_at"] = datetime.utcnow().isoformat()
        
        response = client.table("transcription_jobs").update(update_data).eq("id", job_id).execute()
        return response.data[0] if response.data else None
    
    @classmethod
    async def delete_job(cls, job_id: str) -> bool:
        client = cls.get_service_client()
        if not client:
            raise Exception("Supabase not configured")
        
        client.table("transcription_jobs").delete().eq("id", job_id).execute()
        return True


supabase_service = SupabaseService()
