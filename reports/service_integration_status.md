# Local service verification — 2026-10-09

## Changes

- Health requires an actual Celery worker reply.
- Empty uploads are rejected before storage or dispatch.
- Queue-publication exceptions return HTTP 503 and mark a still-queued job
  failed, preserving state already written by a worker.
- The worker records a missing input artifact as a failure and ignores
  deliveries for jobs no longer queued.
- Fake results identify their model as `fake` and use a canonical category.
- Compose declares a named PostgreSQL volume; the Docker build context excludes
  local environments, datasets, artifacts, and caches.
- Added SQLite-backed API/worker contract tests and a standard-library Compose
  smoke script covering submission, result persistence after worker restart,
  and missing-input failure.

## Verification

- Existing inference suite: **20 passed**, repeated after service changes.
- Python compilation of changed service modules, new tests, and smoke script:
  **passed**.
- Smoke script argument parsing (`--help`): **passed**.
- `docker compose config --quiet`: **passed**.
- `git diff --check`: **passed**.
- New service contract tests: **10 passed** after dependencies were installed.
  The ordinary pytest temporary fixture hits Windows permission errors in this
  agent session. Verification used a temporary local pytest plugin providing
  `tmp_path` from ordinary directories within the workspace; test bodies were
  unchanged. The helper was removed after the run.
- Live PostgreSQL/Valkey/Celery HTTP smoke: **passed** after the stack was
  started externally. `/health` reports database and queue `ok`;
  `POST /jobs` returns HTTP 202 and the fake worker produces a stored
  `SUCCEEDED` result. Verified job:
  `45405d07-3bfd-4023-8e21-7da942443691`.
- A separate HTTP read retrieves the same successful result. Empty videos and
  unsupported file types return HTTP 400; nonexistent job IDs return HTTP 404.
- Worker-restart persistence and injected missing-input failure against the
  live stack: **passed**. The user ran the full smoke command from an external
  PowerShell terminal and supplied all three passing checks. Successful job
  `e4b3b598-5e4f-469d-893b-e39448eb92a6` remained retrievable after worker restart.
  Deliberately failing job `f59df0f8-6e84-4ab5-b508-5a4f2f3f03ed` retained
  `FAILED` with `Input video artifact is missing`. Both final states were
  independently confirmed over HTTP by the agent.
- Temporary setup directories under `.work-tmp` could not be removed: the
  cleanup command was rejected by execution policy. They are excluded from the
  Docker build context.

The local fake-worker integration acceptance checks are complete. The full
Artifact C milestone remains incomplete: the remaining production contracts
still need implementation. Both MinIO/S3 storage and the real GPU worker are
now live-verified separately, including model reuse across two container jobs.
No cloud resources were introduced in this step.

## Next steps

1. MinIO/S3 integration is implemented and live-verified; see
   `minio_integration_status.md` for evidence and repeat-verification commands.
2. Real GPU-worker Docker acceptance and model reuse have passed. See
   `gpu_worker_status.md` for independently confirmed job records and timings.
3. Add migrations, job-control semantics, observability, and broader integration
   coverage before marking Artifact C complete.
