# GPU worker implementation — 2026-10-09

## Implemented

- Real worker path materializes input artifacts in per-job scratch directories,
  supplies optional uploaded transcripts, executes two-pass inference, and
  persists results through the configured artifact store.
- Lazy, process-scoped runner pins the model/processor revision and reuses the
  loaded model across jobs. CUDA initializes inside a Celery child.
- Results record model identity/revision, instance ID, transcript source, and
  download/preparation/generation/model-load timings.
- Summary/category validation and runtime errors produce durable failures.
- API accepts and limits transcript text without a database schema change.
- Separate Python 3.12 GPU image and Compose override reuse the existing API,
  queue, PostgreSQL, and MinIO stack.
- Two-job HTTP acceptance script checks real outputs and process-level reuse.
- Model loading logs use plain text so Windows console encoding does not abort
  an otherwise successful model load.

## Verification

- Service/storage/GPU-runner CPU contract tests: **38 passed**.
- Existing inference tests: **20 passed**.
- Both Compose configurations, compilation, smoke CLI, and whitespace checks:
  **passed**.
- Native real-GPU runner: **passed twice**, same model instance and no repeated
  model-load time. Evidence: `gpu_runner_smoke.json`.
- Hardware/runtime: RTX 2080, Python 3.10.13, Torch 2.8.0+cu126,
  Transformers 4.56.1, cached 500M revision
  `7b375e1b73b11138ff12fe22c8f2822d8fe03467`.
- Model load: 2.195 s. First inference: 22.075 s; second: 20.093 s.
  These are bounded hardware smoke measurements, not a quality benchmark or a
  controlled comparison with the legacy baseline.
- **Container GPU service acceptance passed.** The user built and started the
  GPU Compose override and supplied two passing real-GPU job checks and the
  model-reuse check. The agent independently retrieved both persisted results
  over HTTP and verified success, exact model revision, a shared model instance,
  and zero repeated model-load time. Database, queue, and storage health are all
  `ok`.
- First container job: `1129b3f2-ad6f-4a82-a029-5e14515eeca3`; worker processing
  total 42.888 s, including cold setup, model load 18.803 s, inference 14.938 s.
- Second container job: `23670cc7-1752-4424-8f4e-bdc584d1157a`; worker processing
  total 11.881 s, model load 0 s, inference 11.870 s.
- These totals exclude queue waiting and HTTP upload time. This two-job check
  proves the service path and reuse; it is not a quality/performance baseline.

## Repeat acceptance

Follow `docs/GPU_WORKER_LOCAL.md` to rebuild with the GPU override and run
`scripts.gpu_service_smoke`. This requires two successful HTTP GPU jobs with
the same model instance and no second model load. Evidence from the completed
container check is retained in `gpu_service_smoke.json`.

Current lifecycle/migration acceptance also passed on 2026-10-09, with two new
real GPU jobs and verified warm reuse. See [delivery status](delivery_status.md)
and `local_acceptance.json`. Automatic service-side Whisper transcription,
complete observability, and other production requirements remain unfinished.
