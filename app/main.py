from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from app.core.queue import init_queue
from app.core.database import init_db
from app.core.config import settings
from app.api.routes import router
from app.services.supabase_service import supabase_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database if Supabase not configured
    if not supabase_service.is_configured():
        await init_db()
    await init_queue()
    yield


# Disable docs in production
docs_url = "/docs" if settings.APP_ENV != "production" else None
redoc_url = "/redoc" if settings.APP_ENV != "production" else None

app = FastAPI(
    title="Audio Transcription Service",
    description="Upload audio files and get transcriptions asynchronously",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url="/openapi.json" if settings.APP_ENV != "production" else None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    health_status = {
        "status": "ok",
        "database": "ok",
        "database_type": "supabase" if supabase_service.is_configured() else "sqlite",
        "storage": "ok"
    }
    
    # Check Supabase connection if configured
    if supabase_service.is_configured():
        try:
            client = supabase_service.get_service_client()
            if client:
                # Try a simple query to test connection
                response = client.table("transcription_jobs").select("count", count="exact").limit(0).execute()
        except Exception as e:
            health_status["database"] = f"error: {str(e)}"
    
    return health_status

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
async def root():
    return FileResponse("frontend/index.html")
