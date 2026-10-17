# Local reliability and release demonstration

This runbook uses one Docker Desktop host and an existing RTX 2080. It exercises
an operational service release; it does not claim model-quality promotion, a
remote registry, production high availability or cloud deployment. Keep the
sample and GPU host free of unrelated work. The commands preserve PostgreSQL and
MinIO named volumes; never use `docker compose down -v` for this exercise.
The scripts use the development sample for measured comparability; the public
walkthrough may use the [self-created shapes clip](../assets/portfolio/demo_shapes.mp4).

## Evidence already recorded

- [Current-image GPU smoke](../reports/gpu_service_smoke_current.json): two
  successful real 500M jobs on the rebuilt image and model instance reuse.
- [Admission burst](../reports/admission_demo.json): with a two-job outstanding
  limit, two concurrent jobs were accepted, the third returned 429, and a new
  real GPU job succeeded after the backlog drained. This small burst is not a
  sustained capacity or p95 SLO study.
- [Provisional candidate rejection](../reports/local_demo_gate.json): an
  existing measured 2.2B fewer-frame candidate was rejected under the
  [demo policy](../configs/gates/local-demo.json). This policy is author-selected;
  no 500M production quality promotion follows from it.

## Active-worker interruption

Run from the project PowerShell after the current GPU stack is ready and
`video_jobs_outstanding` is zero:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.recovery_demo --video data/inputs/videos/7203774185322188037.mp4
```

The script temporarily recreates only `dispatcher` and `worker` with a
180-second soft and 240-second hard task limit. It submits a job, waits until
the API records RUNNING, kills the Compose worker with SIGKILL, restarts it,
observes the actual state transitions, requests an explicit retry if the job
fails at its deadline, and verifies a real persisted result. The usual task
limits are restored even if the probe fails. Allow several minutes for deadline
reconciliation. The saved report is `reports/recovery_demo.json`; inspect its
attempts and events when explaining the outcome. A worker kill does not imply
instant resumption or exactly-once execution.

## Operational release and rollback

After recovery has finished and the GPU backlog is empty:

```powershell
& .\scripts\release_demo.ps1
```

The script tags the running API, dispatcher and GPU worker image IDs as the
baseline. It builds the current source as a candidate with a visible
`release_id` in `/health/live`, deploys it, checks readiness, a real job and
the older result, then restores the baseline image IDs. The rollback probe
verifies an older result, the candidate's result and a new real GPU job.
`reports/release_demo_<timestamp>.json` records image IDs, probe paths and
source state. The `release_candidate_...` and `release_rollback_...` reports
contain job IDs and canonical result hashes. The script tags the baseline IDs
back to the ordinary Compose image names after rollback; a future `--build`
will rebuild from the current candidate source.

The [completed report](../reports/release_demo_20261017105931.json) records a
candidate GPU job, a rollback GPU job, exact restoration of all three baseline
image IDs and unchanged hashes for both preserved results. No database migration
or model revision changes are part of this exercise, making the images schema
compatible. The candidate source includes release identity reporting and a
submission idempotency recheck. Image IDs identify the local image bytes; the human-readable tags
are mutable. Source is currently uncommitted, so the report records the Git
commit plus a dirty-tree flag rather than claiming a reproducible commit-based
release. Remote CI execution, signed artifacts and registry promotion still
need separate evidence.

If a probe fails, inspect the saved job ID, attempts/events, Compose logs and
`/metrics`. The release script checks that the backlog is empty before each
switch. If an active job prevents rollback, let it settle and rerun the rollback
with the tagged baseline images; never delete volumes to clear the state.
