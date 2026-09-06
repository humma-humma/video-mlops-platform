from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from sqlalchemy import text

from .config import settings
from .db import SessionLocal, engine, init_db
from .models import Job
from .queue import celery_app
from .schemas import HealthResponse, JobResponse, SubmissionResponse
from .storage import ArtifactStore
from .tasks import process_job


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Video Inference Service", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    try:
        celery_app.control.inspect().ping()
        queue = "ok"
    except Exception:
        queue = "unavailable"
    return HealthResponse(status="ok" if database == queue == "ok" else "degraded", database=database, queue=queue)


@app.post("/jobs", response_model=SubmissionResponse, status_code=202)
async def submit_job(video: UploadFile = File(...)) -> SubmissionResponse:
    if not video.filename or Path(video.filename).suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv"}:
        raise HTTPException(400, "Unsupported video type")
    data = await video.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "Video exceeds upload limit")
    job_id = str(uuid4())
    input_path = ArtifactStore().put_bytes(f"inputs/{job_id}/{Path(video.filename).name}", data)
    with SessionLocal() as db:
        db.add(Job(id=job_id, status="QUEUED", input_path=input_path))
        db.commit()
    process_job.delay(job_id)
    return SubmissionResponse(job_id=job_id, status="QUEUED")


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        result = ArtifactStore().get_json(job.result_path) if job.result_path else None
        return JobResponse(job_id=job.id, status=job.status, result=result, error=job.error_message,
                           created_at=job.created_at, finished_at=job.finished_at)
