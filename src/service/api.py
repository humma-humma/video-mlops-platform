from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from collections import deque
import hashlib
import json
import re
import secrets
import time

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from .config import settings
from .db import SessionLocal, engine, init_db
from .models import Job, JobAttempt, JobEvent
from .queue import celery_app
from .schemas import HealthResponse, JobResponse, SubmissionResponse
from .storage import ArtifactStorageError, ArtifactStore
from .tasks import process_job
from .lifecycle import dispatch_job, record_event
from . import telemetry
from .validation import UploadLimitMiddleware, validate_video
from .demo_ui import install_demo


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Video Inference Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(UploadLimitMiddleware)
install_demo(app)
recent_requests = deque()
OUTSTANDING_STATUSES = ("PENDING", "QUEUED", "RUNNING")


def lock_job_admission(db):
    # Serialize the count and insert/update across API replicas on PostgreSQL.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(84192736)"))


def require_job_capacity(db):
    outstanding = db.scalar(select(func.count()).select_from(Job).where(
        Job.status.in_(OUTSTANDING_STATUSES)))
    if outstanding >= settings.max_outstanding_jobs:
        raise HTTPException(429, "GPU job capacity reached; retry later",
                            headers={"Retry-After": "10"})

def require_auth(x_api_key: str | None = Header(default=None)):
    expected = settings.api_key
    if expected and not secrets.compare_digest(x_api_key or "", expected.get_secret_value()):
        raise HTTPException(401, "Valid API key required")

@app.middleware("http")
async def request_context(request: Request, call_next):
    now = time.monotonic()
    while recent_requests and recent_requests[0] < now - 60:
        recent_requests.popleft()
    counted = request.url.path != "/health/live" and settings.request_rate_limit_per_minute
    limited = counted and len(recent_requests) >= settings.request_rate_limit_per_minute
    if counted and not limited:
        recent_requests.append(now)
    incoming = request.headers.get("traceparent", "")
    match = re.fullmatch(r"00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}", incoming)
    current_trace = match[1] if match and int(match[1], 16) and int(match[2], 16) else uuid4().hex
    token = telemetry.trace_id.set(current_trace)
    status = 500
    try:
        response = (JSONResponse({"detail": "Request rate limit exceeded"}, status_code=429,
                                 headers={"Retry-After": "60"}) if limited else await call_next(request))
        status = response.status_code
        response.headers["traceparent"] = f"00-{current_trace}-{uuid4().hex[:16]}-01"
        return response
    finally:
        route = request.scope.get("route")
        telemetry.observe_request(request.method, route.path if route else "unmatched", status, time.monotonic() - now)
        telemetry.trace_id.reset(token)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    try:
        replies = celery_app.control.inspect(timeout=1.0).ping()
        queue = "ok" if replies else "unavailable"
    except Exception:
        queue = "unavailable"
    try:
        storage = "ok" if ArtifactStore().ready() else "unavailable"
    except (ArtifactStorageError, OSError):
        storage = "unavailable"
    return HealthResponse(
        status="ok" if database == queue == storage == "ok" else "degraded",
        database=database, queue=queue, storage=storage,
    )


@app.post("/jobs", response_model=SubmissionResponse, status_code=202, dependencies=[Depends(require_auth)])
async def submit_job(video: UploadFile = File(...), transcript: str | None = Form(None),
                     idempotency_key: str | None = Header(default=None, min_length=1, max_length=128)) -> SubmissionResponse:
    if not video.filename or Path(video.filename).suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv"}:
        raise HTTPException(400, "Unsupported video type")
    data = await video.read(settings.max_upload_bytes + 1)
    if not data:
        raise HTTPException(400, "Video is empty")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "Video exceeds upload limit")
    if transcript is not None and len(transcript) > settings.max_transcript_chars:
        raise HTTPException(413, "Transcript exceeds length limit")
    suffix = Path(video.filename).suffix.lower()
    request_hash = hashlib.sha256(json.dumps([
        hashlib.sha256(data).hexdigest(), transcript, suffix,
    ], ensure_ascii=False).encode()).hexdigest()
    if idempotency_key:
        with SessionLocal() as db:
            previous = db.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
            if previous:
                if previous.request_hash != request_hash:
                    raise HTTPException(409, "Idempotency key was used with different input")
                return SubmissionResponse(job_id=previous.id, status=previous.status)
    if settings.validate_media:
        try:
            validate_video(data, suffix)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        except (OSError, RuntimeError):
            raise HTTPException(503, "Video inspection unavailable") from None
    job_id = str(uuid4())
    try:
        store = ArtifactStore()
        filename = Path(video.filename.replace("\\", "/")).name
        input_path = store.put_bytes(f"inputs/{job_id}/{filename}", data)
        if transcript is not None:
            store.put_bytes(f"inputs/{job_id}/transcript.txt", transcript.encode("utf-8"))
    except (ArtifactStorageError, OSError):
        raise HTTPException(503, "Artifact storage unavailable") from None
    with SessionLocal() as db:
        lock_job_admission(db)
        if idempotency_key:
            # A concurrent first submission may have committed after our
            # initial pre-upload lookup while filling the last capacity slot.
            previous = db.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
            if previous:
                if previous.request_hash != request_hash:
                    raise HTTPException(409, "Idempotency key was used with different input")
                return SubmissionResponse(job_id=previous.id, status=previous.status)
        require_job_capacity(db)
        job = Job(id=job_id, status="QUEUED", input_path=input_path, generation=0,
                  idempotency_key=idempotency_key, request_hash=request_hash,
                  trace_id=telemetry.trace_id.get())
        db.add(job)
        record_event(db, job, "submitted")
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            previous = db.scalar(select(Job).where(Job.idempotency_key == idempotency_key)) if idempotency_key else None
            if previous is None:
                raise
            if previous.request_hash != request_hash:
                raise HTTPException(409, "Idempotency key was used with different input") from None
            return SubmissionResponse(job_id=previous.id, status=previous.status)
    dispatch_job(job_id, 0)
    return SubmissionResponse(job_id=job_id, status="QUEUED")


@app.get("/jobs/{job_id}", response_model=JobResponse, dependencies=[Depends(require_auth)])
def get_job(job_id: str) -> JobResponse:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        try:
            result = ArtifactStore().get_json(job.result_path) if job.result_path else None
        except (ArtifactStorageError, OSError):
            raise HTTPException(503, "Result artifact unavailable") from None
        return JobResponse(job_id=job.id, status=job.status, result=result, error=job.error_message,
                           created_at=job.created_at, finished_at=job.finished_at)


@app.get("/jobs", response_model=list[JobResponse], dependencies=[Depends(require_auth)])
def list_jobs(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    with SessionLocal() as db:
        jobs = db.scalars(select(Job).order_by(Job.created_at.desc(), Job.id).offset(offset).limit(limit)).all()
        return [JobResponse(job_id=j.id, status=j.status, error=j.error_message,
                            created_at=j.created_at, finished_at=j.finished_at) for j in jobs]

@app.get("/jobs/{job_id}/result", dependencies=[Depends(require_auth)])
def get_result(job_id: str):
    job = get_job(job_id)
    if job.status != "SUCCEEDED":
        raise HTTPException(409, "Job has no successful result")
    return job.result

@app.get("/jobs/{job_id}/attempts", dependencies=[Depends(require_auth)])
def get_attempts(job_id: str):
    with SessionLocal() as db:
        if db.get(Job, job_id) is None:
            raise HTTPException(404, "Job not found")
        attempts = db.scalars(select(JobAttempt).where(JobAttempt.job_id == job_id).order_by(JobAttempt.number)).all()
        return [{"attempt_id": a.id, "number": a.number, "status": a.status,
                 "error_code": a.error_code, "error": a.error_message,
                 "started_at": a.started_at, "finished_at": a.finished_at} for a in attempts]

@app.get("/jobs/{job_id}/events", dependencies=[Depends(require_auth)])
def get_events(job_id: str):
    with SessionLocal() as db:
        if db.get(Job, job_id) is None:
            raise HTTPException(404, "Job not found")
        events = db.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.created_at, JobEvent.id)).all()
        return [{"event": e.event, "generation": e.generation, "trace_id": e.trace_id,
                 "timestamp": e.created_at} for e in events]

@app.post("/jobs/{job_id}/cancel", response_model=SubmissionResponse, dependencies=[Depends(require_auth)])
def cancel_job(job_id: str):
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        if job.status == "CANCELLED":
            return SubmissionResponse(job_id=job_id, status=job.status)
        changed = db.execute(update(Job).where(Job.id == job_id, Job.status.in_(["PENDING", "QUEUED"])).values(
            status="CANCELLED", finished_at=datetime.now(timezone.utc),
        ))
        if not changed.rowcount:
            raise HTTPException(409, "Only a queued job can be cancelled")
        record_event(db, job, "cancelled")
        db.commit()
    return SubmissionResponse(job_id=job_id, status="CANCELLED")

@app.post("/jobs/{job_id}/retry", response_model=SubmissionResponse, status_code=202, dependencies=[Depends(require_auth)])
def retry_job(job_id: str):
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        if job.status != "FAILED" or job.attempts >= settings.max_job_attempts:
            raise HTTPException(409, "Job is not retryable or attempt limit reached")
        lock_job_admission(db)
        require_job_capacity(db)
        generation = job.generation + 1
        changed = db.execute(update(Job).where(
            Job.id == job_id, Job.status == "FAILED", Job.generation == job.generation,
            Job.attempts < settings.max_job_attempts,
        ).values(status="QUEUED", generation=generation, dispatched_at=None,
                 error_message=None, result_path=None, started_at=None, finished_at=None))
        if not changed.rowcount:
            raise HTTPException(409, "Job is not retryable or attempt limit reached")
        record_event(db, job, "retry_requested")
        db.commit()
    dispatch_job(job_id, generation)
    return SubmissionResponse(job_id=job_id, status="QUEUED")

@app.get("/health/live")
def live():
    return {"status": "ok", "release_id": settings.release_id}

@app.get("/health/ready", dependencies=[Depends(require_auth)])
def ready():
    result = health()
    return JSONResponse(result.model_dump(), status_code=200 if result.status == "ok" else 503)

@app.get("/metrics", dependencies=[Depends(require_auth)])
def metrics():
    lines = telemetry.http_metrics()
    with SessionLocal() as db:
        lines.append("# TYPE video_jobs gauge")
        for status, count in db.execute(select(Job.status, func.count()).group_by(Job.status)):
            lines.append(f'video_jobs{{status={json.dumps(status)}}} {count}')
        lines.append("# TYPE video_job_attempts gauge")
        for status, count in db.execute(select(JobAttempt.status, func.count()).group_by(JobAttempt.status)):
            lines.append(f'video_job_attempts{{status={json.dumps(status)}}} {count}')
        oldest = db.scalar(select(func.min(Job.created_at)).where(Job.status == "QUEUED"))
        age = max(0, (datetime.now(timezone.utc) - oldest.replace(tzinfo=timezone.utc)).total_seconds()) if oldest else 0
        lines.append(f"video_oldest_queued_job_seconds {age}")
        lines.append("# TYPE video_job_capacity gauge")
        lines.append(f"video_job_capacity {settings.max_outstanding_jobs}")
        lines.append("# TYPE video_jobs_outstanding gauge")
        lines.append(f"video_jobs_outstanding {db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(OUTSTANDING_STATUSES)))}")
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

# Versioned public routes; legacy paths remain available for existing clients.
for route in list(app.routes):
    if route.path.startswith("/jobs"):
        app.add_api_route("/api/v1" + route.path, route.endpoint, methods=route.methods,
                          response_model=route.response_model, status_code=route.status_code,
                          dependencies=route.dependencies, name="v1_" + route.name)
        route.include_in_schema = False
