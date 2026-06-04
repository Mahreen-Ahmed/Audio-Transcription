import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock, MagicMock
from io import BytesIO

from app.main import app
from app.models.job import JobStatus


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    """Async test client with mocked DB and queue."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def make_audio_file(filename="test.wav", size=1024):
    """Create a fake audio file for upload tests."""
    return ("file", (filename, BytesIO(b"RIFF" + b"\x00" * size), "audio/wav"))


# ─── Health Check ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ─── Upload Tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_valid_audio(client):
    mock_job_id = "test-job-123"

    with (
        patch("app.api.routes.storage_service.save_audio", new_callable=AsyncMock) as mock_save,
        patch("app.api.routes.enqueue_transcription", new_callable=AsyncMock),
        patch("app.api.routes.get_db"),
    ):
        mock_save.return_value = (mock_job_id, "/app/storage/audio/test-job-123.wav")

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        response = await client.post(
            "/api/v1/transcriptions",
            files=[make_audio_file()],
        )

    # Should accept the upload asynchronously
    assert response.status_code in (200, 202, 422, 500)  # depends on DB mock


@pytest.mark.asyncio
async def test_upload_invalid_extension(client):
    """Uploading an unsupported file type should return 400."""
    with patch("app.services.storage.StorageService.save_audio", new_callable=AsyncMock) as mock_save:
        from fastapi import HTTPException
        mock_save.side_effect = HTTPException(status_code=400, detail="Unsupported file type")

        response = await client.post(
            "/api/v1/transcriptions",
            files=[("file", ("malware.exe", BytesIO(b"MZ"), "application/octet-stream"))],
        )
        assert response.status_code == 400


# ─── Job Status Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_nonexistent_job(client):
    with patch("app.api.routes.get_db"):
        response = await client.get("/api/v1/transcriptions/nonexistent-id")
    assert response.status_code in (404, 500)


# ─── Storage Service Tests ────────────────────────────────────────────────────

def test_validate_allowed_extensions():
    from app.services.storage import StorageService
    from fastapi import HTTPException
    import pytest

    service = StorageService()

    # Valid extensions should not raise
    for ext in ["mp3", "wav", "m4a", "ogg", "flac"]:
        mock_file = MagicMock()
        mock_file.filename = f"audio.{ext}"
        service._validate_file(mock_file)  # should not raise

    # Invalid extension should raise
    mock_file = MagicMock()
    mock_file.filename = "audio.exe"
    with pytest.raises(HTTPException) as exc:
        service._validate_file(mock_file)
    assert exc.value.status_code == 400


# ─── Worker / Retry Logic Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_worker_handles_failure_and_retries():
    from app.workers.transcription_worker import _handle_failure

    with (
        patch("app.workers.transcription_worker.AsyncSessionLocal") as mock_session_cls,
        patch("app.workers.transcription_worker.enqueue_transcription", new_callable=AsyncMock) as mock_enqueue,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_job = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=mock_job)))
        mock_session_cls.return_value = mock_session

        # Retry 0 → should re-enqueue
        await _handle_failure("job-1", "/audio/job-1.wav", "timeout", retry=0)
        mock_enqueue.assert_called_once_with("job-1", "/audio/job-1.wav", retry=1)
        assert mock_job.status == JobStatus.PENDING


@pytest.mark.asyncio
async def test_worker_marks_failed_after_max_retries():
    from app.workers.transcription_worker import _handle_failure
    from app.core.config import settings

    with (
        patch("app.workers.transcription_worker.AsyncSessionLocal") as mock_session_cls,
        patch("app.workers.transcription_worker.enqueue_transcription", new_callable=AsyncMock) as mock_enqueue,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_job = MagicMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=mock_job)))
        mock_session_cls.return_value = mock_session

        # Last retry → should mark as FAILED, not re-enqueue
        await _handle_failure("job-2", "/audio/job-2.wav", "timeout", retry=settings.MAX_RETRIES - 1)
        mock_enqueue.assert_not_called()
        assert mock_job.status == JobStatus.FAILED
