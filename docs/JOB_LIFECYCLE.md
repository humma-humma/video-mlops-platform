# Durable job operations

Start with `docker compose up -d --build`. Startup waits for the `migrate` and
`storage-init` services. The dispatcher runs separately from GPU capacity.

Public routes use `/api/v1/jobs`; the existing `/jobs` routes remain compatible.
Submit multipart `video` and optional `transcript`, with an optional
`Idempotency-Key` header. Repeating a key with identical bytes returns the same
job; changing its input returns 409. Keys belong to this single service identity
and remain reserved while their job record exists. This is not multi-tenant auth.

| Operation | Endpoint |
|---|---|
| Submit / paginated list | `POST` / `GET /api/v1/jobs` |
| Inspect status and result | `GET /api/v1/jobs/{id}` |
| Successful result only | `GET /api/v1/jobs/{id}/result` |
| Attempt history / correlated events | `GET /api/v1/jobs/{id}/attempts` / `events` |
| Cancel queued work | `POST /api/v1/jobs/{id}/cancel` |
| Retry a failed job | `POST /api/v1/jobs/{id}/retry` |

Only queued work can be cancelled. Cancellation does not interrupt an active
GPU kernel. Failed-job retries create another generation and attempt; they never
replace the previous attempt artifact. The default maximum is three attempts.

At most two jobs are outstanding by default (`VIDEO_MAX_OUTSTANDING_JOBS`):
PENDING, QUEUED and RUNNING all count. PostgreSQL serializes admission with a
transaction-scoped advisory lock across API replicas; accepted jobs and explicit
or automatic retries use the same limit. A full backlog returns HTTP 429 with
`Retry-After: 10`; idempotent replay of an already accepted request still returns
its original job. This bound protects the single GPU worker from unbounded queued
work; it is separate from the process-local HTTP request-rate limit. The
`video_job_capacity` and `video_jobs_outstanding` gauges expose the configured
limit and current backlog. A rejected upload can leave an orphaned input object
because storage upload precedes the serialized DB admission check; artifact
retention/cleanup remains open.

PostgreSQL is the durable dispatch source. Publication failures leave jobs queued.
The dispatcher retries unpublished jobs and republishes jobs that remain queued
for 120 seconds. Duplicate messages compete for one atomic database claim.
Late results cannot overwrite a timed-out or retried job. A hard-killed worker
may leave RUNNING state until the dispatcher observes the hard deadline plus
60 seconds. Default soft/hard limits are 840/900 seconds.

Artifact-store dependency failures retry after a bounded delay and up to the
same attempt limit. Missing input, invalid output, OOM, and timeout do not loop
automatically. Inspect attempt `error_code`, correlated events, then retry after
fixing the cause. Results use `results/{job_id}/attempt-{number}.json`.

## Validation and access

The API limits request bytes, transcript length, request rate, and duration.
`ffprobe` must find a readable video stream; filenames alone are insufficient.
The lightweight image includes ffmpeg. Upload inspection allows file/pipe
protocols and uses a bounded subprocess timeout.

Compose publishes all ports on loopback. Bundled database/object-store passwords
are local development credentials. Set `VIDEO_API_KEY` in the shell or `.env`
before starting Compose to require `X-API-Key` on job, readiness, and metrics
routes. Smoke clients read the same environment variable. `VIDEO_ENVIRONMENT`
set to staging/production refuses a short/missing key or fake inference.
Compose itself is a local configuration, not a production deployment template.
Rate limiting is per API process; shared ingress controls are required for replicas.

`GET /health/live` checks API process liveness. `/health/ready` returns 503 when
database, worker/queue, or artifact storage is unavailable. `/health` retains its
legacy status-body contract. `/metrics` exposes bounded HTTP labels, job/attempt
state gauges, and oldest queued age. JSON lifecycle logs and stored events carry
the same W3C trace ID; neither includes transcript bodies or generated summaries.
This is correlation, not a complete OpenTelemetry span exporter.

## Migration and recovery

Back up an existing PostgreSQL database before the first upgrade. The Windows
acceptance script does this automatically to `artifacts/backups/`. Alembic adopts
the exact previous unversioned jobs schema, adds lifecycle fields, and retains
old rows/artifact references. It refuses unknown schemas. Old jobs do not acquire
invented historical attempt records. PostgreSQL advisory locking serializes
startup migrations across replicas.

Revision 0002 rollback preserves the original jobs table but deletes new attempt,
event, and idempotency information. Downgrading to base drops jobs. Neither is an
automatic recovery action. Drain workers before image rollback and retain the
additive schema when possible; old workers do not implement generation fencing.

`docker compose down` preserves named volumes. `down -v` destroys data. Do not
use it to fix an upgrade. Orphaned uploads from failed submissions/concurrent
idempotency races and stale unreferenced result objects require a future retention
policy; no automatic destructive cleanup runs in the service.

## Local acceptance

From the project PowerShell:

```powershell
& .\scripts\verify_local.ps1
```

This installs test dependencies into the existing `.venv`, runs all CPU/migration
tests and manifest integrity, rebuilds the fake stack, checks durable storage and
failure behavior, then enables the GPU worker and checks two real jobs/model reuse.
It stops on any failed command, preserves volumes, and writes acceptance evidence
only after all requested checks pass. Use `-SkipGpu` for CPU-only validation.
The existing cached pinned model and Docker GPU support are prerequisites.
