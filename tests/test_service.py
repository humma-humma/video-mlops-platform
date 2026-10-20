"""API/worker contracts using SQLite and an intercepted task publisher.

The real PostgreSQL/Valkey path is covered separately by scripts.service_smoke.
"""

from pathlib import Path
import io
from unittest.mock import Mock
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pydantic import SecretStr

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.service import api, lifecycle, tasks
from src.service.db import Base
from src.service.models import Job, JobAttempt
from src.service.storage import ArtifactStorageError, ArtifactStore


@pytest.fixture
def service(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(api, "engine", engine)
    monkeypatch.setattr(api, "SessionLocal", sessions)
    monkeypatch.setattr(api, "init_db", lambda: Base.metadata.create_all(engine))
    monkeypatch.setattr(tasks, "SessionLocal", sessions)
    monkeypatch.setattr(lifecycle, "SessionLocal", sessions)
    monkeypatch.setattr(api.settings, "artifact_root", str(tmp_path / "artifacts"))
    monkeypatch.setattr(api.settings, "artifact_backend", "filesystem")
    monkeypatch.setattr(tasks.settings, "use_fake_inference", True)
    monkeypatch.setattr(api.settings, "validate_media", False)
    monkeypatch.setattr(api.settings, "request_rate_limit_per_minute", 0)
    monkeypatch.setattr(api.settings, "max_outstanding_jobs", 4)
    monkeypatch.setattr(api.settings, "api_key", None)
    published = []
    monkeypatch.setattr(api.process_job, "delay", lambda job_id, generation=0: published.append(job_id))
    with TestClient(api.app) as client:
        yield client, sessions, published
    engine.dispose()


def submit(client):
    return client.post("/jobs", files={"video": ("sample.mp4", b"fixture", "video/mp4")})


def test_text_deployment_uses_shared_durable_lifecycle(service, monkeypatch):
    client, sessions, _ = service
    routed = []
    monkeypatch.setattr(tasks.process_job, "apply_async", lambda *args, **kwargs: routed.append((args, kwargs)))
    deployments = client.get("/api/v1/deployments").json()
    assert {item["deployment_id"] for item in deployments} == {"video-summary-v1", "text-topic-v1"}
    response = client.post("/api/v1/deployments/text-topic-v1/jobs",
                           json={"text": "Bake bread in the oven"},
                           headers={"Idempotency-Key": "text-1"})
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert routed[0][1]["queue"] == "cpu-inference"
    assert routed[0][1]["args"] == (job_id, 0)
    with sessions() as db:
        assert db.get(Job, job_id).deployment_id == "text-topic-v1"
    tasks.process_job.run(job_id)
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "SUCCEEDED"
    assert job["deployment_id"] == "text-topic-v1"
    assert job["result"]["output"]["label"] == "cooking"
    assert len(job["result"]["model_revision"]) == 64
    assert job["result"]["input_sha256"]
    assert client.get(f"/api/v1/jobs/{job_id}/attempts").json()[0]["status"] == "SUCCEEDED"
    assert client.get("/api/v1/jobs?deployment_id=video-summary-v1").json() == []
    assert len(client.get("/api/v1/jobs?deployment_id=text-topic-v1").json()) == 1
    replay = client.post("/api/v1/deployments/text-topic-v1/jobs",
                         json={"text": "Bake bread in the oven"},
                         headers={"Idempotency-Key": "text-1"})
    assert replay.json()["job_id"] == job_id
    assert len(routed) == 1


def test_text_deployment_validates_input_and_has_separate_capacity(service, monkeypatch):
    client, _, _ = service
    monkeypatch.setattr(tasks.process_job, "apply_async", lambda *args, **kwargs: None)
    monkeypatch.setattr(api.settings, "max_cpu_outstanding_jobs", 1)
    assert client.post("/api/v1/deployments/missing/jobs", json={"text": "hello"}).status_code == 404
    assert client.post("/api/v1/deployments/text-topic-v1/jobs", json={"text": " "}).status_code == 400
    assert client.post("/api/v1/deployments/text-topic-v1/jobs", json={"text": "server"}).status_code == 202
    assert client.post("/api/v1/deployments/text-topic-v1/jobs", json={"text": "database"}).status_code == 429
    assert submit(client).status_code == 202


def test_service_serves_demo_without_bypassing_job_auth(service, monkeypatch):
    client, _, _ = service
    monkeypatch.setattr(api.settings, "api_key", SecretStr("test-demo-key"))
    page = client.get("/")
    assert page.status_code == 200
    assert "Video-MLOps" in page.text
    assert "test-demo-key" not in page.text
    assert client.get("/demo-assets/demo.js").status_code == 200
    assert client.get("/api/v1/jobs").status_code == 401


def test_liveness_reports_effective_release_id(service, monkeypatch):
    client, _, _ = service
    monkeypatch.setattr(api.settings, "release_id", "candidate-demo")
    assert client.get("/health/live").json() == {"status": "ok", "release_id": "candidate-demo"}


def test_submit_process_and_retrieve_persisted_result(service):
    client, sessions, published = service
    response = submit(client)
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert published == [job_id]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "QUEUED"
    tasks.process_job.run(job_id)
    result = client.get(f"/jobs/{job_id}").json()
    assert result["status"] == "SUCCEEDED"
    assert result["result"]["model_version"] == "fake"
    assert result["result"]["category"] == "Daily Life"
    # A repeated delivery after completion must preserve the stored result.
    tasks.process_job.run(job_id)
    assert client.get(f"/jobs/{job_id}").json() == result
    with sessions() as db:
        job = db.get(Job, job_id)
        assert job.attempts == 1
        assert Path(job.result_path).is_file()


@pytest.mark.parametrize("filename,data,status", [
    ("sample.txt", b"fixture", 400),
    ("sample.mp4", b"", 400),
    ("sample.mp4", b"12345", 413),
])
def test_invalid_upload_is_not_dispatched(service, monkeypatch, filename, data, status):
    client, sessions, published = service
    monkeypatch.setattr(api.settings, "max_upload_bytes", 4)
    response = client.post("/jobs", files={"video": (filename, data)})
    assert response.status_code == status
    assert not published
    with sessions() as db:
        assert db.scalars(select(Job)).all() == []


def test_queue_failure_is_recorded_and_reported(service, monkeypatch):
    client, sessions, _ = service

    def unavailable(job_id, generation=0):
        raise ConnectionError("internal broker connection detail")

    monkeypatch.setattr(api.process_job, "delay", unavailable)
    response = submit(client)
    assert response.status_code == 202
    assert "internal" not in response.text
    with sessions() as db:
        job = db.scalars(select(Job)).one()
        assert job.status == "QUEUED"
        assert job.dispatched_at is None
        assert job.error_message is None


def test_publication_acknowledgement_failure_preserves_worker_result(service, monkeypatch):
    client, sessions, _ = service

    def acknowledgement_lost(job_id, generation=0):
        tasks.process_job.run(job_id)
        raise ConnectionError("acknowledgement lost")

    monkeypatch.setattr(api.process_job, "delay", acknowledgement_lost)
    assert submit(client).status_code == 202
    with sessions() as db:
        assert db.scalars(select(Job)).one().status == "SUCCEEDED"


def test_missing_input_records_worker_failure(service):
    client, sessions, _ = service
    job_id = submit(client).json()["job_id"]
    with sessions() as db:
        Path(db.get(Job, job_id).input_path).unlink()
    with pytest.raises(tasks.WorkerFailure, match="Input video artifact is missing"):
        tasks.process_job.run(job_id)
    result = client.get(f"/jobs/{job_id}").json()
    assert result["status"] == "FAILED"
    assert result["error"] == "Input video artifact is missing"
    assert result["result"] is None


def test_unknown_job_returns_404(service):
    client, _, _ = service
    assert client.get("/jobs/unknown").status_code == 404


def test_storage_upload_outage_does_not_create_or_dispatch_a_job(service, monkeypatch):
    client, sessions, published = service

    def unavailable(*args, **kwargs):
        raise ArtifactStorageError("Artifact store request failed")

    monkeypatch.setattr(ArtifactStore, "put_bytes", unavailable)
    response = submit(client)
    assert response.status_code == 503
    assert response.json()["detail"] == "Artifact storage unavailable"
    assert not published
    with sessions() as db:
        assert db.scalars(select(Job)).all() == []


def test_missing_result_artifact_returns_dependency_error(service):
    client, sessions, _ = service
    job_id = submit(client).json()["job_id"]
    tasks.process_job.run(job_id)
    with sessions() as db:
        Path(db.get(Job, job_id).result_path).unlink()
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 503
    assert response.json()["detail"] == "Result artifact unavailable"


def test_result_upload_failure_is_persisted_as_failed_job(service, monkeypatch):
    client, _, _ = service
    job_id = submit(client).json()["job_id"]

    def unavailable(*args, **kwargs):
        raise ArtifactStorageError("Artifact store request failed")

    monkeypatch.setattr(ArtifactStore, "put_json", unavailable)
    with pytest.raises(tasks.WorkerFailure):
        tasks.process_job.run(job_id)
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "FAILED"
    assert job["error"] == "Artifact store request failed"
    assert job["result"] is None
    attempt = client.get(f"/jobs/{job_id}/attempts").json()[0]
    assert attempt["error_code"] == "dependency"
    assert attempt["failure_stage"] == "result_storage"


def test_api_and_worker_use_s3_artifact_uris(service, monkeypatch):
    client, sessions, _ = service
    objects = {}
    s3 = Mock()

    def put_object(*, Bucket, Key, Body):
        objects[Bucket, Key] = Body

    def get_object(*, Bucket, Key):
        return {"Body": io.BytesIO(objects[Bucket, Key])}

    s3.put_object.side_effect = put_object
    s3.get_object.side_effect = get_object
    monkeypatch.setattr(api.settings, "artifact_backend", "s3")
    monkeypatch.setattr(api.settings, "s3_bucket", "test-artifacts")
    monkeypatch.setattr(api, "ArtifactStore", lambda: ArtifactStore(s3_client=s3))
    monkeypatch.setattr(tasks, "ArtifactStore", lambda: ArtifactStore(s3_client=s3))
    job_id = submit(client).json()["job_id"]
    tasks.process_job.run(job_id)
    result = client.get(f"/jobs/{job_id}").json()
    assert result["status"] == "SUCCEEDED"
    with sessions() as db:
        job = db.get(Job, job_id)
        assert job.input_path == f"s3://test-artifacts/inputs/{job_id}/sample.mp4"
        assert job.result_path == f"s3://test-artifacts/results/{job_id}/attempt-1.json"
    assert len(objects) == 2
    s3.head_object.assert_called_once_with(Bucket="test-artifacts", Key=f"inputs/{job_id}/sample.mp4")


@pytest.mark.parametrize("replies,queue", [(None, "unavailable"), ({"worker": {"ok": "pong"}}, "ok")])
def test_health_requires_a_worker_reply(service, monkeypatch, replies, queue):
    client, _, _ = service

    class Inspector:
        def ping(self):
            return replies

    monkeypatch.setattr(api.celery_app.control, "inspect", lambda **kwargs: Inspector())
    result = client.get("/health").json()
    assert result["database"] == "ok"
    assert result["queue"] == queue
    assert result["status"] == ("ok" if queue == "ok" else "degraded")


def test_health_reports_artifact_storage_outage(service, monkeypatch):
    client, _, _ = service
    inspector = Mock()
    inspector.ping.return_value = {"worker": {"ok": "pong"}}
    monkeypatch.setattr(api.celery_app.control, "inspect", lambda **kwargs: inspector)
    monkeypatch.setattr(ArtifactStore, "ready", lambda self: False)
    result = client.get("/health").json()
    assert result["status"] == "degraded"
    assert result["storage"] == "unavailable"


def test_transcript_is_stored_beside_uploaded_video(service):
    client, sessions, _ = service
    response = client.post("/jobs", files={"video": ("sample.mp4", b"fixture")}, data={"transcript": "supplied text"})
    assert response.status_code == 202
    with sessions() as db:
        job = db.get(Job, response.json()["job_id"])
        assert (Path(job.input_path).parent / "transcript.txt").read_text(encoding="utf-8") == "supplied text"


def test_oversized_transcript_is_rejected_before_dispatch(service, monkeypatch):
    client, sessions, published = service
    monkeypatch.setattr(api.settings, "max_transcript_chars", 4)
    response = client.post("/jobs", files={"video": ("sample.mp4", b"fixture")}, data={"transcript": "too long"})
    assert response.status_code == 413
    assert not published
    with sessions() as db:
        assert db.scalars(select(Job)).all() == []


def test_real_worker_downloads_input_and_supplies_transcript(service, monkeypatch, tmp_path):
    client, _, _ = service
    response = client.post("/jobs", files={"video": ("sample.mp4", b"fixture")}, data={"transcript": "supplied text"})
    job_id = response.json()["job_id"]
    monkeypatch.setattr(tasks.settings, "use_fake_inference", False)
    monkeypatch.setattr(tasks.settings, "worker_scratch_root", str(tmp_path))
    monkeypatch.setattr(tasks, "TemporaryDirectory", lambda **kwargs: nullcontext(str(tmp_path)))
    runner = Mock()

    def infer(path, transcript):
        assert path.read_bytes() == b"fixture"
        assert transcript == "supplied text"
        return {"schema_version": "1", "video_id": "sample", "summary": "real adapter result", "category": "Daily Life", "model_version": "test-model", "timings": {}}

    runner.run.side_effect = infer
    from src.service import inference
    from src.service import media
    monkeypatch.setattr(media, "check_first_frame", lambda _: None)
    monkeypatch.setattr(inference, "get_model_runner", lambda: runner)
    tasks.process_job.run(job_id)
    result = client.get(f"/jobs/{job_id}").json()
    assert result["status"] == "SUCCEEDED"
    assert result["result"]["model_version"] == "test-model"
    assert result["result"]["timings"]["total"] >= 0


def test_real_worker_records_inference_failure(service, monkeypatch, tmp_path):
    client, _, _ = service
    job_id = submit(client).json()["job_id"]
    monkeypatch.setattr(tasks.settings, "use_fake_inference", False)
    monkeypatch.setattr(tasks.settings, "worker_scratch_root", str(tmp_path))
    monkeypatch.setattr(tasks, "TemporaryDirectory", lambda **kwargs: nullcontext(str(tmp_path)))
    runner = Mock()
    runner.run.side_effect = RuntimeError("GPU inference failed at category: ValueError")
    from src.service import inference
    from src.service import media
    monkeypatch.setattr(media, "check_first_frame", lambda _: None)
    monkeypatch.setattr(inference, "get_model_runner", lambda: runner)
    with pytest.raises(RuntimeError):
        tasks.process_job.run(job_id)
    result = client.get(f"/jobs/{job_id}").json()
    assert result["status"] == "FAILED"
    assert result["error"] == "GPU inference failed at category: ValueError"


def test_idempotent_submission_replays_same_job_and_rejects_changed_input(service):
    client, _, published = service
    headers = {"Idempotency-Key": "request-1"}
    first = client.post("/api/v1/jobs", files={"video": ("sample.mp4", b"fixture")}, headers=headers)
    replay = client.post("/api/v1/jobs", files={"video": ("sample.mp4", b"fixture")}, headers=headers)
    changed = client.post("/api/v1/jobs", files={"video": ("sample.mp4", b"different")}, headers=headers)
    assert first.status_code == replay.status_code == 202
    assert first.json()["job_id"] == replay.json()["job_id"]
    assert changed.status_code == 409
    assert len(published) == 1


def test_outstanding_capacity_rejects_new_jobs_but_allows_replay_and_recovery(service, monkeypatch):
    client, sessions, published = service
    monkeypatch.setattr(api.settings, "max_outstanding_jobs", 1)
    headers = {"Idempotency-Key": "capacity-original"}
    first = client.post("/api/v1/jobs", files={"video": ("sample.mp4", b"fixture")}, headers=headers)
    assert first.status_code == 202
    replay = client.post("/api/v1/jobs", files={"video": ("sample.mp4", b"fixture")}, headers=headers)
    assert replay.status_code == 202
    assert replay.json()["job_id"] == first.json()["job_id"]
    refused = submit(client)
    assert refused.status_code == 429
    assert refused.headers["Retry-After"] == "10"
    with sessions() as db:
        assert len(db.scalars(select(Job)).all()) == 1
    assert len(published) == 1
    tasks.process_job.run(first.json()["job_id"])
    assert submit(client).status_code == 202


def test_retry_obeys_outstanding_capacity(service, monkeypatch):
    client, sessions, _ = service
    monkeypatch.setattr(api.settings, "max_outstanding_jobs", 1)
    failed_id = submit(client).json()["job_id"]
    with sessions() as db:
        db.get(Job, failed_id).status = "FAILED"
        db.commit()
    active_id = submit(client).json()["job_id"]
    refused = client.post(f"/jobs/{failed_id}/retry")
    assert refused.status_code == 429
    assert refused.headers["Retry-After"] == "10"
    assert client.post(f"/jobs/{active_id}/cancel").status_code == 200
    assert client.post(f"/jobs/{failed_id}/retry").status_code == 202


def test_cancelled_job_is_not_claimed_by_late_delivery(service):
    client, sessions, _ = service
    job_id = submit(client).json()["job_id"]
    assert client.post(f"/api/v1/jobs/{job_id}/cancel").json()["status"] == "CANCELLED"
    tasks.process_job.run(job_id)
    with sessions() as db:
        assert db.get(Job, job_id).attempts == 0
    assert client.get(f"/jobs/{job_id}").json()["status"] == "CANCELLED"


def test_retry_preserves_attempt_history_and_fences_stale_delivery(service):
    client, sessions, _ = service
    job_id = submit(client).json()["job_id"]
    with sessions() as db:
        path = Path(db.get(Job, job_id).input_path)
        path.unlink()
    with pytest.raises(tasks.WorkerFailure):
        tasks.process_job.run(job_id)
    assert client.post(f"/jobs/{job_id}/retry").status_code == 202
    path.write_bytes(b"restored video")
    tasks.process_job.run(job_id, 0)
    assert client.get(f"/jobs/{job_id}").json()["status"] == "QUEUED"
    tasks.process_job.run(job_id, 1)
    history = client.get(f"/jobs/{job_id}/attempts").json()
    assert [a["status"] for a in history] == ["FAILED", "SUCCEEDED"]
    assert history[0]["error_code"] == "missing_input"
    assert client.get(f"/jobs/{job_id}/result").status_code == 200
    assert client.post(f"/jobs/{job_id}/retry").status_code == 409


def test_running_job_cannot_be_cancelled(service):
    client, sessions, _ = service
    job_id = submit(client).json()["job_id"]
    with sessions() as db:
        db.get(Job, job_id).status = "RUNNING"
        db.commit()
    assert client.post(f"/jobs/{job_id}/cancel").status_code == 409


def test_atomic_claim_prevents_concurrent_duplicate_execution(service, monkeypatch):
    client, sessions, _ = service
    job_id = submit(client).json()["job_id"]
    entered, release = Event(), Event()
    original = ArtifactStore.exists

    def delayed_exists(store, uri):
        entered.set()
        assert release.wait(5)
        return original(store, uri)

    monkeypatch.setattr(ArtifactStore, "exists", delayed_exists)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(tasks.process_job.run, job_id)
        try:
            assert entered.wait(5)
            tasks.process_job.run(job_id)
        finally:
            release.set()
        future.result(timeout=5)
    with sessions() as db:
        assert db.get(Job, job_id).attempts == 1
        assert len(db.scalars(select(JobAttempt)).all()) == 1


def test_deferred_dispatch_recovers_after_broker_returns(service, monkeypatch):
    client, sessions, published = service
    publisher = api.process_job.delay
    monkeypatch.setattr(api.process_job, "delay", Mock(side_effect=ConnectionError("offline")))
    job_id = submit(client).json()["job_id"]
    monkeypatch.setattr(api.process_job, "delay", publisher)
    assert lifecycle.dispatch_pending() == 1
    assert published == [job_id]
    with sessions() as db:
        assert db.get(Job, job_id).dispatched_at is not None


def test_reconcile_expired_attempt_fences_late_completion(service, monkeypatch):
    client, sessions, _ = service
    job_id = submit(client).json()["job_id"]
    original_put = ArtifactStore.put_json

    def expire_during_upload(store, key, value):
        with sessions() as db:
            job = db.get(Job, job_id)
            job.started_at = datetime.now(timezone.utc) - timedelta(seconds=api.settings.task_time_limit + 120)
            db.commit()
        assert lifecycle.reconcile_expired() == 1
        return original_put(store, key, value)

    monkeypatch.setattr(ArtifactStore, "put_json", expire_during_upload)
    tasks.process_job.run(job_id)
    result = client.get(f"/jobs/{job_id}").json()
    assert result["status"] == "FAILED"
    assert result["result"] is None
    assert result["error"] == "Worker deadline exceeded"


def test_retry_limit_is_enforced(service, monkeypatch):
    client, _, _ = service
    job_id = submit(client).json()["job_id"]
    monkeypatch.setattr(api.settings, "max_job_attempts", 1)
    monkeypatch.setattr(ArtifactStore, "exists", lambda *args: False)
    with pytest.raises(tasks.WorkerFailure):
        tasks.process_job.run(job_id)
    assert client.post(f"/jobs/{job_id}/retry").status_code == 409


def test_dependency_retry_is_bounded_and_does_not_retry_invalid_input(service, monkeypatch):
    client, sessions, _ = service
    job_id = submit(client).json()["job_id"]
    monkeypatch.setattr(ArtifactStore, "put_json", Mock(side_effect=ArtifactStorageError("offline")))
    with pytest.raises(tasks.WorkerFailure):
        tasks.process_job.run(job_id)
    with sessions() as db:
        attempt = db.scalars(select(JobAttempt)).one()
        attempt.finished_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert lifecycle.retry_dependencies() == 1
    assert lifecycle.retry_dependencies() == 0
    with sessions() as db:
        job = db.get(Job, job_id)
        assert job.status == "QUEUED" and job.generation == 1


def test_api_key_protects_versioned_and_legacy_job_routes(service, monkeypatch):
    client, _, _ = service
    monkeypatch.setattr(api.settings, "api_key", SecretStr("test-key"))
    assert client.get("/jobs").status_code == 401
    assert client.get("/api/v1/jobs").status_code == 401
    assert client.get("/api/v1/jobs", headers={"X-API-Key": "test-key"}).status_code == 200
    assert client.get("/health/live").status_code == 200


def test_trace_is_persisted_without_transcript_content(service):
    client, _, _ = service
    trace = "a" * 32
    response = client.post("/jobs", files={"video": ("sample.mp4", b"fixture")},
                           data={"transcript": "private transcript"},
                           headers={"traceparent": f"00-{trace}-{'b' * 16}-01"})
    job_id = response.json()["job_id"]
    tasks.process_job.run(job_id)
    events = client.get(f"/jobs/{job_id}/events").json()
    assert all(e["trace_id"] == trace for e in events)
    assert "private transcript" not in str(events)
    assert {e["event"] for e in events} >= {"submitted", "running", "succeeded"}


def test_metrics_and_readiness_report_failure(service, monkeypatch):
    client, _, _ = service
    job_id = submit(client).json()["job_id"]
    tasks.process_job.run(job_id)
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert 'video_jobs{status="SUCCEEDED"} 1' in metrics.text
    assert "video_http_requests_total" in metrics.text
    monkeypatch.setattr(ArtifactStore, "ready", lambda self: False)
    assert client.get("/health/ready").status_code == 503


def test_media_validation_rejects_corrupt_upload_before_dispatch(service, monkeypatch):
    client, sessions, published = service
    monkeypatch.setattr(api.settings, "validate_media", True)
    monkeypatch.setattr(api, "validate_video", Mock(side_effect=ValueError("Upload is not a readable video")))
    assert submit(client).status_code == 400
    assert not published
    with sessions() as db:
        assert db.scalars(select(Job)).all() == []


def test_lost_published_message_is_redispatched_and_claimed_once(service):
    client, sessions, published = service
    job_id = submit(client).json()["job_id"]
    with sessions() as db:
        db.get(Job, job_id).dispatched_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.commit()
    assert lifecycle.dispatch_pending() == 1
    assert published == [job_id, job_id]
    tasks.process_job.run(job_id)
    tasks.process_job.run(job_id)
    assert len(client.get(f"/jobs/{job_id}/attempts").json()) == 1


def test_rate_limit_is_bounded_and_returns_retry_after(service, monkeypatch):
    client, _, _ = service
    api.recent_requests.clear()
    monkeypatch.setattr(api.settings, "request_rate_limit_per_minute", 1)
    assert client.get("/jobs").status_code == 200
    response = client.get("/jobs")
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
    assert client.get("/health/live").status_code == 200
    api.recent_requests.clear()
