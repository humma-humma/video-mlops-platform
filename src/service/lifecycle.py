from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, text, update

from .config import settings
from .db import SessionLocal
from .models import Job, JobAttempt, JobEvent
from .storage import ArtifactStorageError
from . import telemetry

def record_event(db, job, name, attempt_id=None):
    db.add(JobEvent(job_id=job.id, generation=job.generation, event=name, trace_id=job.trace_id))
    telemetry.event(name, job_id=job.id, generation=job.generation,
                    attempt_id=attempt_id, trace_id=job.trace_id)

def dispatch_job(job_id: str, generation: int) -> bool:
    from .tasks import process_job
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None or job.status != "QUEUED" or job.generation != generation:
            return False
    try:
        process_job.delay(job_id, generation)
    except Exception:
        # The job itself is the durable outbox. The dispatcher will retry it.
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None and job.status == "QUEUED" and job.generation == generation:
                record_event(db, job, "dispatch_deferred")
                db.commit()
        return False
    with SessionLocal() as db:
        changed = db.execute(update(Job).where(
            Job.id == job_id, Job.generation == generation, Job.status == "QUEUED",
        ).values(dispatched_at=datetime.now(timezone.utc)))
        if changed.rowcount:
            record_event(db, db.get(Job, job_id), "dispatched")
        db.commit()
    return True

def dispatch_pending() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.redispatch_after_seconds)
    with SessionLocal() as db:
        jobs = list(db.execute(select(Job.id, Job.generation).where(
            Job.status == "QUEUED", or_(Job.dispatched_at.is_(None), Job.dispatched_at < cutoff),
        ).order_by(Job.created_at).limit(100)))
    return sum(dispatch_job(job_id, generation) for job_id, generation in jobs)

def reconcile_expired() -> int:
    """Fence timed-out attempts; later deliveries/results cannot replace newer state."""
    now = datetime.now(timezone.utc)
    deadline = now - timedelta(seconds=settings.task_time_limit + 60)
    with SessionLocal() as db:
        jobs = db.scalars(select(Job).where(Job.status == "RUNNING", Job.started_at < deadline)).all()
        count = 0
        for job in jobs:
            changed = db.execute(update(Job).where(
                Job.id == job.id, Job.status == "RUNNING", Job.generation == job.generation,
            ).values(status="FAILED", error_message="Worker deadline exceeded", finished_at=now))
            if not changed.rowcount:
                continue
            db.execute(update(JobAttempt).where(
                JobAttempt.job_id == job.id, JobAttempt.generation == job.generation,
                JobAttempt.status == "RUNNING",
            ).values(status="FAILED", error_code="timeout", error_message="Worker deadline exceeded", finished_at=now))
            record_event(db, job, "deadline_exceeded")
            count += 1
        db.commit()
    return count

def retry_dependencies() -> int:
    deadline = datetime.now(timezone.utc) - timedelta(seconds=settings.retry_backoff_seconds)
    with SessionLocal() as db:
        # The same admission lock as API submissions/retries prevents automatic
        # dependency retries from silently exceeding the GPU backlog limit.
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(84192736)"))
        available = settings.max_outstanding_jobs - db.scalar(
            select(func.count()).select_from(Job).where(Job.status.in_(("PENDING", "QUEUED", "RUNNING"))))
        if available <= 0:
            return 0
        jobs = db.scalars(select(Job).join(JobAttempt, JobAttempt.job_id == Job.id).where(
            Job.status == "FAILED", Job.attempts < settings.max_job_attempts,
            JobAttempt.generation == Job.generation, JobAttempt.error_code == "dependency",
            JobAttempt.finished_at < deadline,
        )).all()
        count = 0
        for job in jobs:
            if count >= available:
                break
            changed = db.execute(update(Job).where(
                Job.id == job.id, Job.status == "FAILED", Job.generation == job.generation,
            ).values(status="QUEUED", generation=Job.generation + 1, dispatched_at=None,
                     started_at=None, finished_at=None, error_message=None, result_path=None))
            if changed.rowcount:
                record_event(db, job, "dependency_retry_requested")
                count += 1
        db.commit()
    return count

def classify_failure(error):
    name = type(error).__name__
    if isinstance(error, FileNotFoundError):
        return "missing_input", "Input video artifact is missing"
    if isinstance(error, ArtifactStorageError):
        return "dependency", "Artifact store request failed"
    if "TimeLimit" in name or isinstance(error, TimeoutError):
        return "timeout", "Worker deadline exceeded"
    if "OutOfMemory" in name:
        return "oom", "GPU memory exhausted"
    if isinstance(error, ValueError):
        return "invalid_output", "Inference returned an invalid result"
    if isinstance(error, RuntimeError) and str(error).startswith("GPU inference failed at "):
        return "inference", str(error)[:120]
    return "internal", "Inference worker failed; inspect correlated events"
