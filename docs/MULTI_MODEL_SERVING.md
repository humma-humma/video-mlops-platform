# Model deployments on the shared job platform

The video VLM is one approved deployment, not the serving platform itself. The
platform now has two code-reviewed adapters in `src/service/deployments.py`:

| Deployment | Input | Worker queue | Model |
| --- | --- | --- | --- |
| `video-summary-v1` | Video file and optional transcript | `video-inference` (GPU in the GPU Compose profile) | Pinned SmolVLM2 revision |
| `text-topic-v1` | JSON text | `cpu-inference` | Tiny, versioned multinomial Naive Bayes artifact |

Both use the same PostgreSQL job, attempt and event records; admission control,
idempotency, artifact storage, retry/reconciliation, and status/result API.
`jobs.deployment_id` is pinned at submission. Migration `0003` assigns existing
jobs to `video-summary-v1` without changing their stored results. Real model
results include their deployment, input hash, model version/revision, stage
timings, attempt ID, and trace ID; fake video results identify themselves as
fake. The operations page shows deployment identity and
per-deployment job counts. Admission limits are shared by CPU/GPU resource
class, so adding another GPU deployment cannot double the GPU backlog. The
video demo filters to video jobs.

## Try the CPU deployment

Start the normal Compose stack (or add `-f docker-compose.gpu.yml` for a real
GPU video worker), then run this from the project PowerShell:

```powershell
docker compose up -d --build --wait
& '.\.venv\Scripts\python.exe' -m scripts.deployment_smoke
```

The script submits a technology-themed text, waits for its persisted result,
checks the artifact revision and shared job history, and prints the job ID.
`GET /api/v1/deployments` lists the approved deployments. JSON submission is
`POST /api/v1/deployments/text-topic-v1/jobs` with `{"text":"..."}`. Video
submission works through either the original `POST /api/v1/jobs` or
`POST /api/v1/deployments/video-summary-v1/jobs` multipart endpoint. Common
status, attempts, events, cancel, retry, and result URLs stay under
`/api/v1/jobs/{job_id}`. An API key is required when `VIDEO_API_KEY` is set.

## Adding another model

Add a reviewed adapter with a stable deployment ID, input kind, resource class,
queue, model description, `run`, and output validation. Register it in
`DEPLOYMENTS`; expose an input validator/submit endpoint for its modality; and
provide a matching worker image and queue. Package an immutable model artifact
or pin a remote revision. Exercise the same failure/recovery contract and add a
task-specific evaluation policy before promoting it. Uploaded model code is
never executed.

The text classifier is deliberately small and trained on 18 illustrative
documents by `scripts/train_text_topic.py`; its scores are not calibrated and
it makes no quality claim. It exists to prove a distinct CPU model can use the
same infrastructure. The existing BERTScore/category release gate still
applies only to the video workload. New tasks need their own held-out data and
quality thresholds before release approval.
