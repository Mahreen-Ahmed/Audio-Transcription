from supabase import create_client, Client
from typing import Optional

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


supabase_service = SupabaseService()
