# 🎙️ Audio Transcription Service

A production-ready async audio transcription API built with **FastAPI**, **OpenAI Whisper**, **PostgreSQL**, and **Redis**. Upload audio files and retrieve transcripts asynchronously via a clean REST API.

---

## Architecture Overview

```
Client
  │
  ▼
┌─────────────────┐        ┌─────────────────┐
│   FastAPI API   │──────▶│   Redis Queue   │
│  (port 8000)    │        │   (arq / BullMQ)│
└────────┬────────┘        └────────┬────────┘
         │                          │
         ▼                          ▼
┌─────────────────┐        ┌─────────────────┐
│   PostgreSQL    │◀───────│  ARQ Worker(s)  │
│   (job state)   │        │ (Whisper model) │
└─────────────────┘        └─────────────────┘
         │
         ▼
┌─────────────────┐
│ Local Storage   │
│ /audio          │
│ /transcripts    │
└─────────────────┘
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/transcriptions` | Upload audio → returns `job_id` (202) |
| `GET` | `/api/v1/transcriptions/{job_id}` | Poll job status + get transcript |
| `GET` | `/api/v1/transcriptions` | List all jobs (paginated, filterable) |
| `DELETE` | `/api/v1/transcriptions/{job_id}` | Delete a job and its audio |
| `GET` | `/health` | Health check |

### Upload Response
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Audio uploaded successfully. Use the job_id to poll for results."
}
```

### Job Status Response
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "original_filename": "interview.mp3",
  "status": "completed",
  "transcript": "Hello, welcome to the interview...",
  "language": "en",
  "duration_seconds": 142.5,
  "retry_count": 0,
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:31:23Z"
}
```

Job `status` values: `pending` → `processing` → `completed` | `failed`

---

## Quick Start

### Prerequisites
- Docker + Docker Compose

### 1. Clone and configure
```bash
git clone <your-repo-url>
cd audio-transcription-service
cp .env.example .env
```

### 2. Start all services
```bash
docker compose up --build
```

This starts:
- **API** on `http://localhost:8000`
- **Worker** (Whisper transcription)
- **PostgreSQL** database
- **Redis** queue

### 3. Try it out
```bash
# Upload an audio file
curl -X POST http://localhost:8000/api/v1/transcriptions \
  -F "file=@your_audio.mp3"

# Poll for result (replace JOB_ID)
curl http://localhost:8000/api/v1/transcriptions/JOB_ID
```

### 4. Interactive docs
Visit `http://localhost:8000/docs` for the Swagger UI.

---

## Design Decisions

### 1. Async Processing with a Job Queue (arq + Redis)

**Problem:** Whisper transcription is CPU-intensive and can take 10–60+ seconds. Blocking the HTTP request would time out clients.

**Decision:** The upload endpoint returns `202 Accepted` immediately with a `job_id`. Processing is handled by background workers pulling from a Redis queue via [arq](https://arq-docs.helpmanual.io/).

**Why arq?** It's built for asyncio Python, lightweight, uses Redis (no extra broker needed), and supports retries and job result storage natively.

---

### 2. PostgreSQL for Job State

**Problem:** Need durable, queryable job state (status, transcript, timestamps).

**Decision:** PostgreSQL with SQLAlchemy async ORM. Job rows track the full lifecycle: `pending → processing → completed/failed`.

**Why not Redis alone?** Redis is ephemeral and not ideal for durable business data. PostgreSQL gives us ACID guarantees, easy querying, and pagination.

---

### 3. Retry with Exponential Backoff + Dead Letter

**Problem:** Transcription can fail due to corrupted audio, OOM, or transient errors.

**Decision:**
- Workers catch exceptions and re-enqueue with increasing delays: `30s → 2min → 10min`
- After 3 retries, job is marked `failed` (dead letter pattern)
- Each retry is logged with the error message for auditability

---

### 4. File Storage Strategy

**Problem:** Audio files can be large (100MB+) and transcripts need to be retrievable.

**Decision:**
- **Audio** → stored on disk at `/storage/audio/{job_id}.{ext}` (production: swap for S3)
- **Transcripts** → stored both in PostgreSQL (for fast API response) and as `.txt` files on disk
- Files are streamed in 1MB chunks during upload to avoid loading the whole file into memory

**Production note:** Replace local disk storage with S3/GCS using the same interface — only `StorageService` needs updating.

---

### 5. Whisper Model on CPU

**Decision:** Using `openai-whisper` locally with `fp16=False` for CPU compatibility. Default model is `base` (good accuracy/speed tradeoff).

**Model selection guide** (set `WHISPER_MODEL` in `.env`):
| Model | RAM | Speed | Accuracy |
|-------|-----|-------|----------|
| tiny | ~1GB | Fastest | Low |
| base | ~1GB | Fast | Good ← **default** |
| small | ~2GB | Moderate | Better |
| medium | ~5GB | Slow | Great |
| large | ~10GB | Slowest | Best |

---

### 6. Concurrent Uploads

**How it works:**
- Multiple clients can upload simultaneously — each gets an independent `job_id`
- The API is non-blocking (async FastAPI + asyncpg)
- Workers process up to 5 jobs concurrently (`max_jobs = 5` in WorkerSettings)
- File streaming prevents memory spikes during concurrent uploads

---

## Running Tests

```bash
# Inside Docker
docker compose exec api pytest tests/ -v

# Locally (with venv)
pip install -r requirements.txt
pytest tests/ -v
```

---

## Project Structure

```
audio-transcription-service/
├── app/
│   ├── api/
│   │   └── routes.py          # REST API endpoints
│   ├── core/
│   │   ├── config.py          # Settings (pydantic-settings)
│   │   ├── database.py        # SQLAlchemy async engine
│   │   └── queue.py           # Redis/arq queue setup
│   ├── models/
│   │   ├── job.py             # SQLAlchemy ORM model
│   │   └── schemas.py         # Pydantic request/response schemas
│   ├── services/
│   │   ├── storage.py         # File upload/save logic
│   │   └── transcriber.py     # Whisper transcription logic
│   ├── workers/
│   │   └── transcription_worker.py  # ARQ worker + retry logic
│   └── main.py                # FastAPI app entry point
├── tests/
│   └── test_api.py            # Unit + integration tests
├── storage/
│   ├── audio/                 # Uploaded audio files
│   └── transcripts/           # Saved transcript text files
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```
