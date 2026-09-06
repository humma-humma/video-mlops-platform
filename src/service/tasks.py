from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .db import SessionLocal
from .models import Job
from .queue import celery_app
from .storage import ArtifactStore


@celery_app.task(bind=True, max_retries=2)
def process_job(self, job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status, job.started_at, job.attempts = "RUNNING", datetime.now(timezone.utc), job.attempts + 1
        db.commit()
        try:
            if settings.use_fake_inference:
                result = {"schema_version": "1", "video_id": Path(job.input_path).stem,
                          "summary": "Fake inference result for local integration testing.",
                          "category": "Other", "model_version": settings.model_name,
                          "timings": {"total": 0.0}}
            else:
                raise RuntimeError("GPU inference adapter is not enabled in this worker profile")
            result_path = ArtifactStore().put_json(f"results/{job.id}.json", result)
            job.result_path, job.status, job.finished_at = result_path, "SUCCEEDED", datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            job.status, job.error_message, job.finished_at = "FAILED", str(exc), datetime.now(timezone.utc)
            db.commit()
            raise
