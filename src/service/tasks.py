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
from .deployments import get_deployment
from .lifecycle import classify_failure, record_event
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
            stage = "artifact_check"
            store = ArtifactStore()
            adapter = get_deployment(job.deployment_id)
            if not store.exists(job.input_path):
                raise FileNotFoundError("Input video artifact is missing" if adapter.input_kind == "video"
                                        else "Input artifact is missing")
            if adapter.input_kind == "video" and settings.use_fake_inference:
                result = {"schema_version": "1", "video_id": Path(job.input_path).stem,
                          "summary": "Fake inference result for local integration testing.",
                          "category": "Daily Life", "model_version": "fake",
                          "timings": {"total": 0.0}}
            else:
                start = time.perf_counter()
                stage = "scratch_setup"
                scratch_root = Path(settings.worker_scratch_root)
                scratch_root.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(dir=scratch_root) as temporary:
                    stage = "input_download"
                    local_input = Path(temporary) / Path(job.input_path).name
                    store.download_file(job.input_path, local_input)
                    transcript = ""
                    if adapter.input_kind == "video":
                        transcript_uri = (
                            job.input_path.rsplit("/", 1)[0] + "/transcript.txt"
                            if job.input_path.startswith("s3://")
                            else str(Path(job.input_path).parent / "transcript.txt")
                        )
                        transcript = store.get_bytes(transcript_uri).decode("utf-8") if store.exists(transcript_uri) else ""
                    download_time = time.perf_counter() - start
                    stage = "inference"
                    result = adapter.run(local_input, {"transcript": transcript})
                    result["input_sha256"] = sha256_file(local_input)
                    import hashlib
                    if adapter.input_kind == "video":
                        result["transcript_sha256"] = hashlib.sha256(transcript.encode()).hexdigest()
                    result["timings"]["input_download"] = download_time
                    result["timings"]["total"] = time.perf_counter() - start
            stage = "result_validation"
            result = adapter.validate_result(result)
            result["deployment_id"] = adapter.deployment_id
            result.update(attempt_id=attempt.id, trace_id=job.trace_id)
            stage = "result_storage"
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
            if code in {"decode_failed", "decode_timeout", "decoder_unavailable"}:
                stage = "decode_preflight"
            event("worker_failure", job_id=job_id, deployment_id=job.deployment_id,
                  generation=generation, attempt_id=attempt.id, stage=stage,
                  error_type=type(exc).__name__, error_code=code, trace_id=job.trace_id)
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
