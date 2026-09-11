# Project Status

**Last updated:** 2026-09-11  
**Canonical repository:** <https://github.com/humma-humma/video-mlops-platform>  
**Current milestone:** Artifact C local integration

This document is the source of truth for current implementation status. The
roadmap in `PLATFORM_IMPLEMENTATION_PLAN.md` describes intended scope; items in
that document are not complete unless recorded as verified here.

## Status summary

| Area | State | Evidence |
|---|---|---|
| Inference core | Implemented and CPU-tested | 20 unit tests pass |
| Real GPU smoke path | Verified with economical model | SmolVLM2-500M on RTX 2080; report in `reports/gpu_smoke.json` |
| Artifact C service skeleton | Implemented | FastAPI, SQLAlchemy/PostgreSQL, Celery/Valkey, local artifact adapter |
| Docker Compose definition | Validated statically | `docker compose config --quiet` passes |
| Artifact C live end-to-end path | Blocked / unverified | Docker Desktop commands stalled during build and status checks |
| Artifact D lifecycle | Not started | No MLflow registry, evaluation gate, CI/CD, or cloud deployment |
| Artifact E retrieval | Not started | No timestamp segmentation, pgvector indexing, or citation pipeline |

## Verified capabilities

- Canonical category taxonomy with normalization and validation.
- Deterministic video/transcript alignment and a checksummed dataset manifest.
- Injectable inference boundary for model-free unit tests.
- Per-video timings, structured failures, and partial-batch isolation.
- Existing-transcript handling with cached Whisper fallback.
- Automatic FP16 selection on GPUs without BF16 support.
- Two-pass summary/category inference and guarded fallback when combined JSON
  generation fails.
- Real CUDA inference using `HuggingFaceTB/SmolVLM2-500M-Video-Instruct`:
  model loading and schema-valid two-pass output completed on an RTX 2080.
- FastAPI endpoints for submission, retrieval, and health reporting.
- PostgreSQL-backed job state and Celery task dispatch through Valkey.
- CPU-compatible fake worker mode for inexpensive service integration tests.
- Portfolio-safe packaging that excludes raw videos, transcripts, model
  weights, generated benchmark outputs, caches, and local service state.

## Current blockers

### B1 — Docker runtime is not completing operations

`docker compose up --build` exceeded the available execution window, and
subsequent `docker compose ps` calls also stalled. Compose syntax is valid, but
the API-to-queue-to-worker path has therefore not been demonstrated live.

**Unblock:** restart/repair Docker Desktop, confirm `docker info` and
`docker run --rm hello-world` complete promptly, then run the Artifact C
acceptance test documented below.

### B2 — Worker is not connected to real inference

The Compose worker defaults to fake inference. Setting
`VIDEO_USE_FAKE_INFERENCE=false` currently raises an explicit runtime error;
there is no production adapter that loads the existing inference core once per
worker process and executes a submitted video.

**Unblock:** add a GPU-worker image/profile and a process-scoped model runner,
then test one submitted video against the downloaded 500M checkpoint.

### B3 — MinIO is declared but not used

The service persists inputs and results through a shared filesystem volume.
MinIO is present in Compose, but the artifact abstraction has no S3-compatible
implementation yet.

**Unblock:** implement and test an S3/MinIO adapter, bucket bootstrap, object
keys, and failure handling; retain the filesystem adapter for unit tests.

## Known production gaps

These are planned work, not environmental blockers:

- Replace `Base.metadata.create_all()` with versioned Alembic migrations.
- Add idempotency keys, cancellation, explicit retry endpoints, and auditable
  attempts.
- Add validated result contracts at the worker/database boundary.
- Add structured logs, Prometheus metrics, traces, readiness semantics, and
  redaction.
- Add authentication, rate limiting, upload-content validation, retention, and
  cleanup policies.
- Add API, database, queue, artifact-store, worker-failure, and restart
  integration tests.
- Add separate lightweight API and CUDA worker images.

## Current acceptance checks

Verified on 2026-09-11:

```text
pytest:                         20 passed
docker compose config:         passed
uv lock --check:               passed (202 packages resolved)
real GPU smoke inference:      passed previously
live Compose job submission:   not yet verified
```

Artifact C can be marked locally complete only when this sequence passes:

1. `docker compose up --build` reaches healthy API, PostgreSQL, Valkey, and
   worker services.
2. A sample video submitted to `POST /jobs` returns HTTP 202 immediately.
3. `GET /jobs/{job_id}` progresses from `QUEUED` to `RUNNING` to `SUCCEEDED`.
4. The result remains retrievable after the worker restarts.
5. An intentionally failing job reaches `FAILED` with a useful error record.
6. The same flow passes once with the fake worker and once with the GPU worker.

## Next actions

1. Restore reliable Docker Desktop operation and complete the fake-worker
   end-to-end acceptance test.
2. Replace shared-volume artifacts with the MinIO adapter.
3. Connect the real GPU inference runner and validate model reuse across jobs.
4. Add migrations, job-control semantics, observability, and integration tests.
5. Begin Artifact D only after Artifact C's local acceptance checks pass.
