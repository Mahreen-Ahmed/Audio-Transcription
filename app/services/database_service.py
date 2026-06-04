from typing import Optional, Dict, Any, List
from datetime import datetime

from app.models.job import TranscriptionJob, JobStatus
from app.core.database import AsyncSessionLocal
from sqlalchemy import select, func
from app.services.supabase_service import supabase_service


class DatabaseService:
    @classmethod
    def _use_supabase(cls) -> bool:
        return supabase_service.is_configured()

    @classmethod
    async def create_job(cls, job_id: str, original_filename: str, audio_path: str) -> Dict[str, Any]:
        if cls._use_supabase():
            return await supabase_service.create_job(job_id, original_filename, audio_path)
        else:
            async with AsyncSessionLocal() as session:
                job = TranscriptionJob(
                    id=job_id,
                    original_filename=original_filename,
                    audio_path=audio_path,
                    status=JobStatus.PENDING
                )
                session.add(job)
                await session.commit()
                await session.refresh(job)
                return cls._job_to_dict(job)

    @classmethod
    async def get_job(cls, job_id: str) -> Optional[Dict[str, Any]]:
        if cls._use_supabase():
            return await supabase_service.get_job(job_id)
        else:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TranscriptionJob).where(TranscriptionJob.id == job_id)
                )
                job = result.scalar_one_or_none()
                return cls._job_to_dict(job) if job else None

    @classmethod
    async def list_jobs(cls, status: Optional[str] = None, page: int = 1, page_size: int = 10) -> tuple[List[Dict[str, Any]], int]:
        if cls._use_supabase():
            return await supabase_service.list_jobs(status, page, page_size)
        else:
            async with AsyncSessionLocal() as session:
                query = select(TranscriptionJob)
                count_query = select(func.count(TranscriptionJob.id))

                if status:
                    query = query.where(TranscriptionJob.status == status)
                    count_query = count_query.where(TranscriptionJob.status == status)

                total = (await session.execute(count_query)).scalar()

                query = (
                    query.order_by(TranscriptionJob.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                jobs = (await session.execute(query)).scalars().all()

                return [cls._job_to_dict(job) for job in jobs], total

    @classmethod
    async def update_job_status(cls, job_id: str, status: str, **kwargs) -> Optional[Dict[str, Any]]:
        if cls._use_supabase():
            return await supabase_service.update_job_status(job_id, status, **kwargs)
        else:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TranscriptionJob).where(TranscriptionJob.id == job_id)
                )
                job = result.scalar_one_or_none()

                if not job:
                    return None

                job.status = status
                job.updated_at = datetime.now(datetime.UTC)

                for key, value in kwargs.items():
                    if hasattr(job, key):
                        setattr(job, key, value)

                if status == "completed":
                    job.completed_at = datetime.now(datetime.UTC)

                await session.commit()
                await session.refresh(job)
                return cls._job_to_dict(job)

    @classmethod
    async def delete_job(cls, job_id: str) -> bool:
        if cls._use_supabase():
            return await supabase_service.delete_job(job_id)
        else:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TranscriptionJob).where(TranscriptionJob.id == job_id)
                )
                job = result.scalar_one_or_none()

                if not job:
                    return False

                await session.delete(job)
                await session.commit()
                return True

    @classmethod
    def _job_to_dict(cls, job: TranscriptionJob) -> Dict[str, Any]:
        return {
            "id": job.id,
            "original_filename": job.original_filename,
            "audio_path": job.audio_path,
            "status": job.status.value if hasattr(job.status, "value") else job.status,
            "transcript": job.transcript,
            "language": job.language,
            "duration_seconds": job.duration_seconds,
            "error_message": job.error_message,
            "retry_count": job.retry_count,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None
        }


database_service = DatabaseService()
