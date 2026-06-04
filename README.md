# 🎙️ Audio Transcription Service

A production-ready async audio transcription API built with **FastAPI**, **OpenAI Whisper**, **PostgreSQL**, **Redis**, and **Supabase**. Upload audio files and retrieve transcripts asynchronously via a clean REST API.

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
└────────┬────────┘        └─────────────────┘
         │
         ▼
┌─────────────────┐
│  Supabase (or)  │
│  Local Storage  │
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
| `GET` | `/health` | Health check (includes Supabase status) |

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
- (Optional) Supabase account

### 1. Clone and configure
```bash
git clone <your-repo-url>
cd audio-transcription-service
cp .env.example .env
```

### 2. (Optional) Set up Supabase
1. Go to https://supabase.com and create a project
2. Get your credentials from Project Settings → API
3. Add to `.env`:
   ```env
   SUPABASE_URL=https://<project-id>.supabase.co
   SUPABASE_ANON_KEY=<your-anon-key>
   SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
   ```
4. Create two storage buckets in Supabase:
   - `audio-files` (for uploaded audio)
   - `transcripts` (for saved transcriptions)
5. Add these policies to both buckets:
   ```sql
   -- For audio-files bucket
   CREATE POLICY "Allow authenticated uploads"
   ON storage.objects FOR INSERT TO authenticated
   WITH CHECK (bucket_id = 'audio-files');

   CREATE POLICY "Allow public downloads"
   ON storage.objects FOR SELECT
   USING (bucket_id = 'audio-files');

   -- For transcripts bucket
   CREATE POLICY "Service role can manage files"
   ON storage.objects FOR ALL
   TO service_role
   USING (bucket_id = 'transcripts');
   ```
6. (Optional) Create the `transcription_jobs` table in Supabase with the SQL provided earlier

### 3. Start all services
```bash
docker compose up --build
```

This starts:
- **API** on `http://localhost:8000`
- **Worker** (Whisper transcription)
- **PostgreSQL** database
- **Redis** queue

### 4. Try it out
```bash
# Upload an audio file
curl -X POST http://localhost:8000/api/v1/transcriptions \
  -F "file=@your_audio.mp3"

# Poll for result (replace JOB_ID)
curl http://localhost:8000/api/v1/transcriptions/JOB_ID
```

### 5. Interactive docs
Visit `http://localhost:8000/docs` for the Swagger UI.

---

## Design Decisions

### 1. Async Processing with a Job Queue (arq + Redis)

**Problem:** Whisper transcription is CPU-intensive and can take 10–60+ seconds. Blocking the HTTP request would time out clients.

**Decision:** The upload endpoint returns `202 Accepted` immediately with a `job_id`. Processing is handled by background workers pulling from a Redis queue via [arq](https://arq-docs.helpmanual.io/).

**Why arq?** It's built for asyncio Python, lightweight, uses Redis (no extra broker needed), and supports retries and job result storage natively.

---

### 2. Supabase for Database & Storage

**Problem**: Need durable, queryable job state and object storage for audio/transcripts, without managing separate services.

**Decision**: Use Supabase (built on PostgreSQL) for both database and object storage:
- **Database**: `transcription_jobs` table tracks the full job lifecycle: `pending → processing → completed/failed`
- **Storage**: `audio-files` bucket for uploaded audio, `transcripts` bucket for saved transcript files

**Why Supabase?**
- One platform handles both database and storage, reducing operational complexity
- Built on PostgreSQL, giving ACID guarantees, easy querying, and pagination
- Object storage with CDN, signed URLs, and security policies
- Generous free tier for development

---

### 3. Retry with Exponential Backoff + Dead Letter

**Problem:** Transcription can fail due to corrupted audio, OOM, or transient errors.

**Decision:**
- Workers catch exceptions and re-enqueue with increasing delays: `30s → 2min → 10min`
- After 3 retries, job is marked `failed` (dead letter pattern)
- Each retry is logged with the error message for auditability

---

### 4. File Storage Strategy (with Supabase)

**Problem:** Audio files can be large (100MB+) and transcripts need to be retrievable.

**Decision:**
- **Primary: Supabase Storage**: When configured, uses Supabase's durable object storage with automatic CDN
- **Fallback: Local Disk**: Seamless fallback for development or if Supabase is unavailable
- **Audio** → stored in `audio-files` bucket (or `/storage/audio/{job_id}.{ext}` locally)
- **Transcripts** → stored both in PostgreSQL (for fast API response) and in `transcripts` bucket (or as `.txt` files locally)
- **Unified Interface**: `StorageService` abstracts storage details, making it easy to swap providers

---

### 5. Whisper Model on CPU with Anti-Repetition Settings

**Decision:**
- Using `openai-whisper` locally with `fp16=False` for CPU compatibility
- Default model is `base` (good accuracy/speed tradeoff)
- Added `no_speech_threshold=0.6` and `condition_on_previous_text=False` to reduce repetition loops

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
│   │   ├── storage.py         # File upload/save (local + Supabase)
│   │   ├── transcriber.py     # Whisper transcription logic
│   │   └── supabase_service.py # Supabase client
│   ├── workers/
│   │   └── transcription_worker.py  # ARQ worker + retry logic
│   └── main.py                # FastAPI app entry point
├── tests/
│   └── test_api.py            # Unit + integration tests
├── storage/
│   ├── audio/                 # Uploaded audio files (local fallback)
│   └── transcripts/           # Saved transcript text files (local fallback)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```
