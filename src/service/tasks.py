from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from uuid import uuid4
from src.lineage import sha256_file
from sqlalchemy import update

from .config import settings
from .db import SessionLocal
from .models import Job, JobAttempt
from .queue import celery_app
from .storage import ArtifactStore
from .inference import get_model_runner
from .lifecycle import classify_failure, record_event
from .schemas import InferenceResult
from .telemetry import event

class WorkerFailure(RuntimeError):
    """Sanitized task error; original dependency exceptions stay out of logs."""


@celery_app.task(bind=True, max_retries=0)
def process_job(self, job_id: str, generation: int = 0) -> None:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        claim = db.execute(update(Job).where(
            Job.id == job_id, Job.status == "QUEUED", Job.generation == generation,
        ).values(status="RUNNING", started_at=now, attempts=Job.attempts + 1))
        if not claim.rowcount:
            db.rollback()
            return
        job = db.get(Job, job_id)
        attempt = JobAttempt(id=str(uuid4()), job_id=job.id, number=job.attempts,
                             generation=generation, status="RUNNING", started_at=now)
        db.add(attempt)
        record_event(db, job, "running", attempt.id)
        db.commit()
        try:
            store = ArtifactStore()
            if not store.exists(job.input_path):
                raise FileNotFoundError("Input video artifact is missing")
            if settings.use_fake_inference:
                result = {"schema_version": "1", "video_id": Path(job.input_path).stem,
                          "summary": "Fake inference result for local integration testing.",
                          "category": "Daily Life", "model_version": "fake",
                          "timings": {"total": 0.0}}
            else:
                start = time.perf_counter()
                scratch_root = Path(settings.worker_scratch_root)
                scratch_root.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(dir=scratch_root) as temporary:
                    local_video = Path(temporary) / Path(job.input_path).name
                    store.download_file(job.input_path, local_video)
                    transcript_uri = (
                        job.input_path.rsplit("/", 1)[0] + "/transcript.txt"
                        if job.input_path.startswith("s3://")
                        else str(Path(job.input_path).parent / "transcript.txt")
                    )
                    transcript = store.get_bytes(transcript_uri).decode("utf-8") if store.exists(transcript_uri) else ""
                    download_time = time.perf_counter() - start
                    result = get_model_runner().run(local_video, transcript)
                    result["input_sha256"] = sha256_file(local_video)
                    import hashlib
                    result["transcript_sha256"] = hashlib.sha256(transcript.encode()).hexdigest()
                    result["timings"]["input_download"] = download_time
                    result["timings"]["total"] = time.perf_counter() - start
            result = InferenceResult.model_validate(result).model_dump()
            result.update(attempt_id=attempt.id, trace_id=job.trace_id)
            result_path = store.put_json(f"results/{job.id}/attempt-{attempt.number}.json", result)
            finished = datetime.now(timezone.utc)
            changed = db.execute(update(Job).where(
                Job.id == job_id, Job.status == "RUNNING", Job.generation == generation,
            ).values(result_path=result_path, status="SUCCEEDED", finished_at=finished, error_message=None))
            if not changed.rowcount:
                db.rollback()
                event("stale_result_discarded", job_id=job_id, generation=generation, attempt_id=attempt.id)
                return
            attempt.result_path, attempt.status, attempt.finished_at = result_path, "SUCCEEDED", finished
            record_event(db, job, "succeeded", attempt.id)
            db.commit()
        except Exception as exc:
            code, message = classify_failure(exc)
            finished = datetime.now(timezone.utc)
            changed = db.execute(update(Job).where(
                Job.id == job_id, Job.status == "RUNNING", Job.generation == generation,
            ).values(status="FAILED", error_message=message, finished_at=finished))
            if not changed.rowcount:
                db.rollback()
                raise WorkerFailure("Stale job execution failed") from None
            attempt.status, attempt.error_code = "FAILED", code
            attempt.error_message, attempt.finished_at = message, finished
            record_event(db, job, "failed", attempt.id)
            db.commit()
            raise WorkerFailure(message) from None
