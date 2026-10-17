# Artifact C: local asynchronous service

Start the stack with `docker compose up --build`. The API is available at
`http://localhost:8000/docs` and uses a fake inference worker by default so the
integration path is free and CPU-compatible. Submit a video with:

```bash
curl -F video=@sample.mp4 http://localhost:8000/jobs
curl http://localhost:8000/jobs/<job_id>
```

Set `VIDEO_USE_FAKE_INFERENCE=false` only in a GPU worker image that includes
the model runtime; see [the GPU worker runbook](GPU_WORKER_LOCAL.md).
PostgreSQL is authoritative for job state; Valkey is only
the queue. Compose now stores uploaded videos and generated results in MinIO;
the filesystem backend remains the default outside Compose for unit tests.

## Acceptance check

Confirm Docker Desktop's Linux engine is running with `docker info`, then:

```bash
docker compose up --build -d
python -m scripts.service_smoke --video data/inputs/videos/7203774185322188037.mp4 --restart-worker --check-failure --check-storage
```

The standard-library smoke script requires a healthy database and a responding
Celery worker, submits a video through HTTP, polls for a successful fake result,
restarts the worker and verifies that the result remains retrievable, and queues
a deliberately missing input to verify a persistent `FAILED` record. It uses
bounded HTTP requests, subprocess calls, and polling. The failure check creates
one test job through `docker compose exec`; it does not expose a public fault
injection endpoint. `--check-storage` verifies that both database artifact
references are S3 URIs and that the uploaded object and result are readable
from MinIO. Uploaded smoke inputs and job records remain available for
inspection. The API now inspects video streams using ffprobe; this fake-worker
check does not verify model inference. See [job operations](JOB_LIFECYCLE.md)
for migrations, retries, cancellation, security, and consolidated acceptance.

PostgreSQL, MinIO, and legacy filesystem artifacts use named volumes.
`docker compose down` retains them; `docker compose down -v` deletes them.
If an older stack has data in PostgreSQL's anonymous volume, migrate or back up
that data before recreating PostgreSQL with the new named volume.

Run API/worker contract tests without Docker or model downloads:

```bash
python -m pip install -r requirements-service-test.txt
python -m pytest tests/test_service.py tests/test_storage.py -q
```

These tests use SQLite and intercept queue publication. The Compose smoke check
is required separately to verify PostgreSQL, Valkey, and a real Celery worker.

## Artifact storage configuration

The `storage-init` Compose service retries bucket initialization while MinIO
starts. API and worker startup wait until initialization succeeds. Only this
explicit bootstrap creates the bucket; normal reads/writes do not create it.
MinIO stores objects in the `minio_data` volume. Its console is available at
`http://localhost:9001`, using the development credentials in Compose.

Outside Compose, set `VIDEO_ARTIFACT_BACKEND=s3` and configure
`VIDEO_S3_ENDPOINT_URL`, `VIDEO_S3_BUCKET`, `VIDEO_S3_REGION`,
`VIDEO_S3_ACCESS_KEY_ID`, and `VIDEO_S3_SECRET_ACCESS_KEY` as needed. An omitted
endpoint uses AWS S3; omitted credentials use the SDK credential chain. No
cloud resources are created by the local Compose configuration. The bundled
MinIO credentials are for local development.

Stored references use `s3://<bucket>/<key>`. Existing local references remain
readable through the retained shared volume; there is no automatic data copy.
Missing objects produce explicit worker failures. Storage outages return HTTP
503 on submission/result retrieval, and `/health` includes storage readiness.
