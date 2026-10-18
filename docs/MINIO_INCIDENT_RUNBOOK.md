# Live MinIO interruption acceptance

The host-side `scripts.minio_incident_demo` tests a real storage dependency failure against the existing local Compose stack. It does not rebuild images, remove volumes, submit a video or change model configuration. It briefly stops the dispatcher, CPU worker and MinIO; all three are started again in a `finally` block. The GPU worker is untouched. The API may show degraded storage readiness during the interruption, so run this only on the local demo stack when no other jobs are active.

From the project PowerShell with Docker Desktop and the stack running:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.minio_incident_demo
```

The script checks service readiness, all three container states and an empty job backlog before acting. It queues a small text-model job while its CPU worker and dispatcher are stopped. It then stops MinIO and starts **only the existing CPU-worker container** with `docker start`; Compose's `start cpu-worker` also starts MinIO as a dependency and would invalidate the experiment. A real S3 `head_object` request should fail, producing a durable failed attempt with service code `dependency`. The script correlates exactly one structured worker-failure log to that job, hashes the selected log line and exports a redacted bundle while the job is failed. It restarts MinIO, waits for readiness, requests an explicit retry and verifies a successful second attempt and persisted result.

Expected terminal ending:

```text
services_restored
PASS real MinIO interruption, durable failure and recovered result: <job-id>
Evidence: reports\diagnostics\minio-live\incident.json
```

`reports/diagnostics/minio-live/run_state.json` records the steps and restoration outcome even when the run fails. `incident.json`, `failed_job.json` and `recovered_job.json` are written on success. The bundle and report exclude raw job IDs, text input, trace IDs, free-form errors and logs. The terminal prints the job ID for local troubleshooting. Do not treat the collected log hash as an independent signature of the Docker runtime; it identifies the exact line the script parsed.

Analyze the failed bundle offline:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench analyze --bundle reports/diagnostics/minio-live/failed_job.json
```

Expected evidence-level finding: `reported_artifact_check_failure`. The bundle cites the `dependency` attempt code and `artifact_check` worker stage. The experiment ledger establishes that MinIO was intentionally stopped, but the analyzer does not read that ledger or infer a downstream S3 cause from the two fields alone. This is one local CPU-job incident, not a GPU or decoder measurement. If the script fails, inspect `run_state.json` and confirm `docker compose -f docker-compose.yml -f docker-compose.gpu.yml ps`; a queued or failed test job may need manual review. Do not delete named volumes.

The [2026-10-18 acceptance run](../reports/diagnostics/minio-live/incident.json) recorded `FAILED` then `SUCCEEDED` attempts for the same job. Its [restoration state](../reports/diagnostics/minio-live/run_state.json) has `completed: true` and no restoration errors. The [failed](../reports/diagnostics/minio-live/failed_job.json) and [recovered](../reports/diagnostics/minio-live/recovered_job.json) bundles validate against the schema and their hashes match the incident ledger. The [single-case evaluation](../reports/diagnostics/minio-live/evaluation.json) matches the pre-specified evidence-level label and both citations resolve. It does not estimate performance on independent incidents.
