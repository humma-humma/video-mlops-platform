# Video ML Platform Implementation Plan

## 1. Objective

Extend the existing SmolVLM2 video summarization benchmark into a coherent, portfolio-ready platform containing:

1. **Artifact C:** an asynchronous GPU video inference service.
2. **Artifact D:** an inference experiment, evaluation-gate, registry, and deployment lifecycle.
3. **Optional partial Artifact E:** a searchable video knowledge base with timestamped citations.

The implementation must remain useful as a research benchmark while adding production behavior around it. The project will be built and verified locally first. Paid cloud infrastructure is introduced only after the equivalent local workflow passes its acceptance tests.

The existing [MLOPS_PLAN.md](MLOPS_PLAN.md) remains useful background. This document is the execution plan for the larger service and lifecycle scope and supersedes its ordering where the two differ.

### Implementation status — 2026-08-29

Work has started on G0/G1:

- Added a shared, versioned taxonomy used by prompting and evaluation.
- Added explicit category-evaluation coverage and noncanonical-label reporting.
- Added a deterministic, checksummed dataset manifest with documented exclusions.
- Preserved the historical benchmark as a documented legacy reference without restoring deleted generated artifacts.
- Corrected Python/FlashAttention portability metadata, declared the downloader dependency, and regenerated `uv.lock`.
- Added a pure, injectable orchestration boundary for deterministic video selection, transcript/prompt preparation, and two-pass inference.
- Cached Whisper pipeline loading per model/device and made the fallback device configurable.
- Added isolated two-pass and strict combined-generation strategies with per-video timings and structured failures.
- Added automatic FP16 fallback for GPUs without BF16 support.
- Expanded the CPU test suite from 2 to 20 passing tests.

Still required before G1 is fully closed:

- Install/sync the complete locked runtime in the target GPU environment.
- Record real per-video latency distributions after the model checkpoint is available.
- Compare two-pass and combined quality/latency on the versioned evaluation subset.
- Run and record a new real-GPU baseline with exact model/processor revisions.

## 2. Success Definition

The complete project should demonstrate the following path:

```text
video submission
    -> durable asynchronous job
    -> GPU inference
    -> versioned result artifacts
    -> quality and operational metrics
    -> reproducible experiment
    -> candidate evaluation gate
    -> registered inference bundle
    -> versioned container
    -> staging deployment
```

The optional retrieval path adds:

```text
timestamped transcript segments
    -> embeddings in PostgreSQL/pgvector
    -> filtered retrieval
    -> evidence-grounded response
    -> video/timestamp citations
    -> retrieval evaluation
```

The project is complete when another developer can clone it, run tests, start the full local stack with one documented command, submit a job, observe its execution, retrieve its result, reproduce a benchmark, and understand why a candidate deployment passed or failed.

## 3. Scope Boundaries

### Included

- Video summary and category inference using an open-source VLM.
- Existing-transcript loading with an optional Whisper fallback.
- Asynchronous single-video and batch jobs.
- Input validation, durable status, retries, failure records, health endpoints, and structured logs.
- PostgreSQL metadata, a Redis-compatible queue, and S3-compatible artifact storage.
- Local Docker Compose environment with GPU worker support.
- MLflow experiment tracking and an inference-bundle registry.
- Dataset manifests, prompt versions, exact model revisions, and image digests.
- Automated evaluation and latency/quality regression gates.
- Unit, integration, API, worker, and small end-to-end tests.
- GitHub Actions for CI, container publishing, candidate benchmarking, and staging deployment.
- One AWS deployment path.
- Monitoring for service, model, and data-quality behavior.
- Optional timestamp-aware retrieval using PostgreSQL and pgvector.

### Explicitly excluded from the critical path

- A frontend; Swagger/OpenAPI and a CLI are sufficient.
- Real-time streaming inference.
- Multi-cloud deployment.
- Kubernetes before the AWS/ECS deployment works.
- Terraform/OpenTofu before the AWS deployment works manually.
- General-purpose agents or LangGraph in the core pipeline.
- Full model training merely to claim a training pipeline.
- Five vector databases, multiple queues, or multiple orchestration frameworks.

### Possible future extension

LoRA fine-tuning can later add a genuine training-candidate lifecycle. Until then, Artifact D is accurately described as an **inference bundle and deployment lifecycle**, not a training lifecycle.

## 4. Economic Constraints and Cost Policy

### Default policy

1. Prefer open-source, self-hosted components locally.
2. Reuse the existing GPU rather than renting one during development.
3. Do not run the full VLM in ordinary GitHub-hosted CI.
4. Do not keep a cloud GPU running while idle.
5. Do not create paid AWS resources until the local Compose acceptance test passes.
6. Create an AWS budget and billing alarms before creating compute resources.
7. Tag every cloud resource with `project`, `environment`, `owner`, and `expires_at`.
8. Maintain separate `demo` and `production-reference` infrastructure profiles.
9. Destroy the demo environment after recorded demonstrations unless it is actively needed.
10. Treat credits and free tiers as discounts, not architectural assumptions.

### Free-first local stack

| Capability | Local choice | Cost posture |
|---|---|---|
| API | FastAPI, Pydantic, Uvicorn | Open source |
| Queue/worker | Celery with Valkey | Open source |
| Metadata | PostgreSQL | Open source |
| Object storage | S3-compatible local object store | Self-hosted |
| Experiment tracking | MLflow | Open source, self-hosted |
| Metrics | Prometheus | Open source |
| Dashboards | Grafana OSS | Open source |
| Tracing | OpenTelemetry with a local collector/Jaeger | Open source |
| Containers | Docker Engine/Compose | Free locally; observe Docker Desktop terms |
| Infrastructure as code | OpenTofu-compatible HCL | Open source |
| Retrieval | PostgreSQL with pgvector | No extra database |

### Cloud cost controls

- Run the API on CPU capacity and isolate the VLM worker on GPU capacity.
- Configure the GPU Auto Scaling group with a desired capacity of zero outside demonstrations.
- Use Spot GPU capacity for interruptible benchmarks; use on-demand only when reliability is required.
- Set short CloudWatch log retention for staging.
- Apply S3 lifecycle rules to temporary uploads and intermediate artifacts.
- Apply ECR lifecycle rules and retain only a small number of images.
- Avoid a NAT Gateway in the portfolio demo profile if a safe public-egress design or VPC endpoints are sufficient; document the production security trade-off.
- Keep multi-AZ databases and high availability in the production reference design, not the continuously running demo.
- Run a cost estimate and review the planned resource diff before every cloud apply.

## 5. Target Architecture

### 5.1 Local and logical architecture

```text
CLI / Swagger / API client
          |
          v
     FastAPI service --------------------------+
          |                                    |
          | create/query job                   | presigned upload/download
          v                                    v
     PostgreSQL                            Object store
          |                                    ^
          | enqueue                            |
          v                                    |
        Valkey                                 |
          |                                    |
          v                                    |
      Celery worker ----------------------------+
          |
          +--> SmolVLM2 inference
          +--> optional Whisper transcription
          +--> evaluation jobs
          +--> MLflow tracking/registry

All services -> JSON logs, Prometheus metrics, OpenTelemetry traces
```

### 5.2 AWS mapping

| Logical component | AWS deployment |
|---|---|
| API | ECS service on CPU/Fargate capacity behind an Application Load Balancer |
| GPU worker | ECS task on an EC2 GPU capacity provider |
| Job database | RDS PostgreSQL |
| Queue/cache | ElastiCache-compatible service in the production reference; self-hosted Valkey is allowed in the temporary demo profile |
| Artifacts | S3 |
| Images | ECR |
| Logs/metrics | CloudWatch, with OpenTelemetry export where useful |
| Secrets | Secrets Manager or SSM Parameter Store |
| Identity | Least-privilege IAM task roles and GitHub OIDC deployment role |

### 5.3 Ownership rules

- PostgreSQL is authoritative for job state and externally visible results.
- Valkey is transient coordination infrastructure, never the only copy of a result.
- The object store owns uploaded videos, transcripts, large predictions, and reports.
- MLflow owns experiment metadata, evaluation runs, and registered inference bundles.
- Git owns source, prompts, configuration schemas, database migrations, infrastructure definitions, and small dataset manifests.
- Large videos and generated artifacts do not belong in Git.

## 6. Core Data Contracts

Define these contracts before building the service so the CLI, API, worker, database, and evaluator use the same vocabulary.

### Job states

```text
PENDING -> QUEUED -> RUNNING -> SUCCEEDED
                         |-> FAILED
PENDING/QUEUED -> CANCELLED
FAILED -> QUEUED  (explicit retry creates an auditable new attempt)
```

### Minimum job record

- `job_id`
- `job_type`: `inference`, `batch_inference`, `evaluation`, or `indexing`
- `status`
- `input_artifact_uri`
- `result_artifact_uri`
- `model_name` and exact `model_revision`
- `processor_revision`
- `prompt_version`
- `taxonomy_version`
- `inference_config_hash`
- `dataset_manifest_hash`, when applicable
- `attempt_count`
- `created_at`, `queued_at`, `started_at`, and `finished_at`
- `error_code`, `error_message`, and `error_artifact_uri`
- `trace_id`

### Inference result schema

```json
{
  "schema_version": "1",
  "video_id": "...",
  "summary": "...",
  "category": "Travel & Events",
  "model_version": "...",
  "prompt_version": "...",
  "timings": {
    "transcript": 0.0,
    "video_decode": 0.0,
    "generation": 0.0,
    "postprocess": 0.0,
    "total": 0.0
  }
}
```

Validate worker output with Pydantic before committing job success.

### Idempotency

- Accept an `Idempotency-Key` on job submission.
- Enforce uniqueness per caller and operation for a bounded retention period.
- A retry must not silently overwrite an earlier attempt.
- Artifact keys include job and attempt identifiers.

## 7. Repository Evolution

Refactor incrementally; do not move every file in one change.

```text
configs/
  experiments/
  service/
docs/
  adr/
  operations/
infra/
  compose/
  aws/
  kubernetes/              # later phase
migrations/
reports/
scripts/
src/
  api/
    main.py
    routes/
    schemas.py
  core/
    config.py
    logging.py
  domain/
    jobs.py
    results.py
  pipeline/
    inference.py
    transcripts.py
    evaluation.py
    prompts.py
  services/
    artifacts.py
    jobs.py
  workers/
    celery_app.py
    tasks.py
  tracking/
    mlflow_utils.py
  retrieval/               # optional phase
tests/
  unit/
  integration/
  e2e/
  fixtures/
```

The existing CLI should call `src.pipeline` rather than being deleted. This provides a cheap debug path and keeps batch benchmarking useful.

## 8. Delivery Roadmap

Estimates are focused engineering days and exclude long GPU benchmarks, cloud quota approval, and waiting for external services. Artifact C plus Artifact D is approximately **25-35 focused days**. The optional retrieval extension is another **5-8 days**. Each phase has a stop/go gate; later work should not begin while its dependency gate is failing.

### Phase 0 — Baseline, decisions, and safety rails (1-2 days)

**Goal:** establish an honest, reproducible starting point.

Tasks:

- Preserve or restore one known benchmark result before changing inference behavior.
- Record the current Git commit, data inventory, model revision, environment, and GPU.
- Resolve the category taxonomy mismatch between prompts and ground truth.
- Decide how the duplicated video and the six missing videos are represented in the dataset manifest.
- Fix declared dependencies, including the downloader dependency.
- Replace the incomplete local environment with a reproducible `uv sync` flow.
- Add formatter/linter/type-check decisions and pin them in project metadata.
- Add Architecture Decision Records for:
  - PostgreSQL as the job source of truth.
  - Valkey/Celery for asynchronous work.
  - S3-compatible artifacts.
  - MLflow for experiment and bundle tracking.
  - AWS as the single cloud.
- Create a cost-policy document and prohibit untagged AWS resources.

Verification:

- A clean environment can install the project.
- `main.py --help` works.
- Existing tests pass.
- The manifest reports exactly which inputs are usable, missing, or duplicated.
- The baseline result and configuration are traceable.

**Gate G0:** no service refactor begins until the baseline is reproducible and the taxonomy contract is explicit.

### Phase 1 — Stabilize and isolate the inference core (2-4 days)

**Goal:** turn the script into a testable library without changing its validated output unexpectedly.

Tasks:

- Separate configuration, transcript preparation, inference, post-processing, evaluation, and persistence.
- Replace implicit dictionaries with Pydantic/dataclass contracts where they cross boundaries.
- Make the model runner injectable so tests can use a fake implementation.
- Load Whisper once per worker process rather than once per missing transcript.
- Remove hard-coded CUDA device selection from transcript handling.
- Record per-video, per-stage timings rather than placeholder aggregate statistics.
- Record failures per video and allow a batch to finish when one item fails.
- Sort and align inputs deterministically by `video_id`.
- Validate empty evaluation sets and duplicate IDs explicitly.
- Add prompt and taxonomy version identifiers.
- Evaluate a single structured generation that emits both summary and category, because it may avoid decoding/encoding every video twice. Keep the two-pass path until quality and latency are compared.

Tests:

- Prompt construction and output parsing.
- Category normalization and allowed-label enforcement.
- Dataset alignment by `video_id`.
- Existing transcript, missing transcript, no-audio, and failed-Whisper paths.
- Stage timing/statistics calculations.
- Partial batch failure.
- Fake-model end-to-end CLI run.

Verification:

- Unit tests do not download a model or require a GPU.
- The fake-model CLI produces valid CSV and JSON artifacts.
- A small real-GPU sample produces schema-valid output.
- Baseline quality stays within an explicitly approved tolerance.

**Gate G1:** the pipeline is callable as a library and its tests run without GPU access.

### Phase 2 — Config-driven experiments and data lineage (2-3 days)

**Goal:** make every benchmark reproducible without copied command lines.

Tasks:

- Introduce validated YAML experiment configurations.
- Convert the Slurm variants to named configurations or generated launch scripts.
- Add CLI overrides without permitting unknown keys.
- Pin the Hugging Face model and processor to exact revisions.
- Create dataset manifests containing:
  - logical dataset version
  - video ID and checksum
  - transcript checksum
  - ground-truth checksum
  - split and inclusion/exclusion reason
- Hash prompt, taxonomy, preprocessing, and inference configurations.
- Decide after a short spike whether DVC adds useful lineage beyond Git manifests plus object-store versioning. Do not add it only for name recognition.

Verification:

- Repeating an experiment config yields the same resolved configuration hash.
- A manifest integrity command identifies altered or missing files.
- Every output records model, dataset, prompt, taxonomy, code, and config versions.

**Gate G2:** a result is not accepted unless its complete lineage can be reconstructed.

### Phase 3 — Service persistence and API skeleton (2-3 days)

**Goal:** accept and inspect durable jobs before asynchronous GPU work is added.

Tasks:

- Add FastAPI with versioned `/api/v1` routes.
- Add PostgreSQL models and Alembic migrations.
- Implement job creation, retrieval, listing, and result schemas.
- Implement upload validation:
  - MIME/container checks
  - extension allowlist
  - maximum size and duration
  - safe generated object keys
  - rejection of arbitrary filesystem paths
- Add object-store abstraction and local S3-compatible implementation.
- Add idempotent submission.
- Add `/health/live` and dependency-aware `/health/ready`.
- Generate and commit an OpenAPI schema snapshot or validate it in CI.

Minimum endpoints:

```text
POST /api/v1/jobs
GET  /api/v1/jobs/{job_id}
GET  /api/v1/jobs/{job_id}/result
POST /api/v1/jobs/{job_id}/retry
POST /api/v1/jobs/{job_id}/cancel
GET  /health/live
GET  /health/ready
GET  /metrics
```

Verification:

- API tests run against temporary PostgreSQL and object storage.
- Duplicate idempotent requests return the same logical job.
- Invalid videos are rejected before queue submission.
- Migrations apply from an empty database and can roll back the latest revision.

**Gate G3:** a submitted job is durable and inspectable even if the worker is offline.

### Phase 4 — Asynchronous GPU worker and failure semantics (3-4 days)

**Goal:** complete Artifact C behavior.

Tasks:

- Configure Celery and Valkey.
- Implement a worker task that loads the VLM once per process.
- Make queue names and worker concurrency explicit; default GPU concurrency to one until measured.
- Persist state transitions transactionally.
- Add bounded retries only for retryable failures.
- Classify validation, decode, dependency, OOM, timeout, and internal failures.
- Add soft/hard timeouts and cleanup of temporary files.
- Add worker heartbeat/readiness.
- Make result upload happen before the database commits `SUCCEEDED`.
- Implement cancellation semantics honestly; queued cancellation is required, while running cancellation may be cooperative.
- Add a CLI client that submits a job and polls for completion.

Verification:

- API remains responsive while a long job runs.
- Restarting the API does not lose jobs.
- Worker failure produces a durable `FAILED` record.
- A retry creates an auditable attempt and does not overwrite old artifacts.
- A successful result validates against the public schema.
- A fake worker exercises all flows without a GPU.

**Gate G4 / Artifact C MVP:** submit, validate, process asynchronously, store, retrieve, fail, retry, log, and report health through documented interfaces.

### Phase 5 — Docker Compose production-like local stack (2-3 days)

**Goal:** run Artifact C locally with one command.

Tasks:

- Add separate multi-stage images for API and CUDA worker.
- Run containers as non-root users where GPU/runtime requirements allow.
- Use a persistent model-cache volume rather than baking model weights into images.
- Add Compose services for API, worker, PostgreSQL, Valkey, object storage, and MLflow.
- Add health checks and startup dependencies based on health, not fixed sleeps.
- Put credentials in ignored environment files or Docker secrets.
- Add CPU/fake-worker and GPU Compose profiles.
- Add volume backup/reset documentation.
- Measure image size and remove build tools/caches from runtime layers.

Verification:

```text
docker compose --profile test up --build
docker compose --profile gpu up --build
```

- The test profile completes an end-to-end fake job.
- The GPU profile completes one real video job.
- Container restart preserves PostgreSQL and artifact data.
- Swagger is accessible and health endpoints report correct dependency state.

**Gate G5:** the documented Compose command works from a fresh clone after required model/data setup.

### Phase 6 — MLflow, evaluation, and candidate gates (3-4 days)

**Goal:** turn benchmark runs into Artifact D candidates.

Tasks:

- Log resolved parameters, metrics, tags, and artifacts to MLflow.
- Track:
  - model and processor revisions
  - prompt/taxonomy versions
  - dataset manifest hash
  - Git commit and image digest
  - stage latency, throughput, and peak GPU memory
  - failure rate
  - BERTScore and category metrics
- Generate a benchmark report comparing candidates to the current production baseline.
- Define configurable absolute floors and relative regression tolerances.
- Register successful **inference bundles**, containing model reference, processor, prompts, taxonomy, preprocessing, runtime config, and output schema.
- Require a human-readable reason when a gate is overridden.
- Separate online inference jobs from offline evaluation jobs.

Candidate flow:

```text
candidate config
    -> versioned evaluation subset
    -> metrics and artifacts in MLflow
    -> compare with production bundle
    -> pass/fail decision
    -> register bundle if passed
```

Verification:

- A deliberately degraded candidate fails the gate.
- An approved candidate becomes a traceable registry version.
- The report links back to raw predictions, config, manifest, and Git commit.
- Re-running the gate does not silently change the baseline.

**Gate G6:** no bundle is deployable without lineage, evaluation, and an explicit gate result.

### Phase 7 — Observability, operations, and security baseline (2-4 days)

**Goal:** make behavior diagnosable rather than merely logged.

Tasks:

- Emit structured JSON logs with `job_id`, `attempt_id`, `video_id`, `bundle_version`, and `trace_id`.
- Propagate trace context through API, queue, worker, model stages, database, and object storage.
- Export Prometheus metrics for:
  - request rate/errors/latency
  - queue depth and wait time
  - job success/failure/retry rates
  - stage and total inference latency
  - throughput
  - GPU memory/utilization when available
  - missing transcript and decode failures
  - predicted category and summary-length distributions
- Add Grafana dashboards and explicit alert thresholds.
- Add log redaction and prevent transcripts/secrets from appearing in routine logs.
- Add request limits, authentication for non-local deployments, and least-privilege service identities.
- Document backup/restore, stuck-job recovery, model rollback, and incident response.

Verification:

- One trace follows a request from submission through worker completion.
- A forced failure is visible in job state, logs, metrics, and trace data.
- Readiness fails when a required dependency is unavailable.
- Secrets and raw uploaded content do not appear in standard logs.

**Gate G7:** a failed job can be diagnosed from telemetry without reproducing it interactively.

### Phase 8 — CI and local delivery automation (2-3 days)

**Goal:** automate cheap checks and isolate expensive GPU checks.

GitHub Actions workflows:

1. `ci.yml`, on pull request:
   - dependency installation
   - formatting/linting/type checks
   - unit tests
   - API and worker tests with fakes
   - migration checks
   - OpenAPI compatibility check
2. `integration.yml`, on pull request or merge:
   - start Compose test profile
   - submit and retrieve a fake job
   - scan images and generate an SBOM
3. `containers.yml`, on protected-branch merge/tag:
   - build immutable API/worker images
   - tag with Git SHA and release version
   - push to registry
4. `benchmark.yml`, manual/scheduled:
   - run on a self-hosted or temporary cloud GPU runner
   - evaluate candidate bundle
   - publish MLflow run and gate report
5. `deploy.yml`, only after a passed gate:
   - authenticate to AWS with GitHub OIDC
   - deploy staging
   - run smoke tests
   - require approval before production

Economic rules:

- No full-model download or GPU inference in ordinary CI.
- Use small generated fixtures and a fake runner.
- Retain CI artifacts only as long as needed.
- Cache dependencies carefully; model weights are not normal CI cache artifacts.

Verification:

- A breaking schema or migration change fails CI.
- A worker/API contract mismatch fails integration testing.
- Registry push and deployment cannot occur from an untrusted pull request.
- Deployment is cryptographically tied to an image digest and registered bundle.

**Gate G8:** Artifact C and D changes cannot merge without cheap deterministic checks.

### Phase 9 — Manual AWS staging deployment (3-5 days)

**Goal:** prove the cloud architecture manually before automating infrastructure creation.

Tasks:

- Create budget alarms, resource tags, and a teardown checklist first.
- Create VPC/subnets/security groups with documented demo-versus-production trade-offs.
- Deploy S3, RDS PostgreSQL, queue service, ECR, ECS API, and ECS GPU worker capacity.
- Configure least-privilege task roles and secret injection.
- Put the API behind an Application Load Balancer with TLS.
- Configure GPU worker capacity to scale toward zero.
- Set log retention and storage/image lifecycle rules.
- Deploy a registered bundle to staging.
- Run service, failure, restart, and rollback smoke tests.
- Record actual costs for the demonstration period.

Verification:

- A remote client submits a video without receiving AWS credentials.
- API and database have no unnecessary public access.
- Worker reads only required input objects and writes only its job prefix.
- A failed deployment rolls back to the previous task definition/bundle.
- GPU capacity returns to zero after the configured idle interval.
- Teardown removes all non-retained resources.

**Gate G9:** manual staging deployment and teardown are both proven before infrastructure as code is written.

### Phase 10 — OpenTofu/Terraform-compatible infrastructure and CD (2-4 days)

**Goal:** reproduce the validated AWS setup.

Tasks:

- Encode networking, IAM, ECR, S3, RDS, queue, ECS, load balancer, logging, budgets, and alarms.
- Separate reusable modules only where more than one environment uses them.
- Use remote state with locking and documented recovery.
- Add `demo` and `production-reference` variable sets.
- Add plan review in CI; apply only through protected environments.
- Add automated staging deployment and post-deploy smoke tests.
- Keep production apply manual/approved.
- Add an explicit destroy workflow for temporary demo environments.

Verification:

- A fresh staging environment can be created from code.
- A second plan after apply has no unexplained drift.
- Destroy removes temporary resources without deleting retained artifacts unexpectedly.
- CI cannot expose secrets or obtain broader AWS permissions than needed.

**Gate G10 / Artifact D MVP:** a gated candidate can be registered, built, deployed to reproducible staging, tested, and rolled back.

### Phase 11 — Kubernetes learning deployment (P1, 3-5 days)

**Goal:** demonstrate Kubernetes concepts without replacing the working ECS path.

Tasks:

- Deploy API and fake worker to kind/minikube first.
- Add Deployment, Service, Ingress, ConfigMap, Secret, readiness/liveness probes, resource requests/limits, and rolling-update strategy.
- Represent one-off evaluation/indexing as Jobs.
- Keep PostgreSQL and object storage external in the production design.
- Add a GPU worker manifest and document NVIDIA device-plugin requirements; local kind success does not require real GPU inference.
- Add autoscaling only after queue and resource metrics are available.

Verification:

- Local cluster handles rollout, failed readiness, and rollback.
- API stays available during a rolling update.
- A worker cannot be scheduled without its declared resources.
- Configuration differs by environment without image rebuilds.

**Gate G11:** Kubernetes is a demonstrated alternative deployment target, not a second unfinished production platform.

### Phase 12 — Optional timestamped video retrieval (5-8 days)

**Goal:** add the useful portion of Artifact E without turning the service into a generic agent demo.

Prerequisites:

- Store timestamped Whisper segments or create an explicit alignment step; the current plain transcripts cannot support honest timestamp citations.
- Finish Artifact C and the evaluation framework first.

Tasks:

- Enable pgvector in the existing PostgreSQL deployment.
- Define timestamped transcript chunks with video/category/language metadata.
- Generate embeddings with a pinned open-source embedding model.
- Add lexical retrieval and dense retrieval; combine them only if evaluation supports hybrid search.
- Add metadata filtering and a reranking experiment.
- Return citations containing `video_id`, start/end timestamps, and evidence text.
- Add an evaluation set covering:
  - known evidence
  - missing evidence
  - conflicting evidence
  - metadata-filtered queries
  - adversarial/instruction-like transcript content
- Track Recall@k, MRR, hit rate, citation correctness, groundedness, and latency.
- Add a deterministic retrieval-and-answer pipeline first.
- Add a router or tool-calling layer only if there are multiple genuine tools, such as retrieval, SQL analytics, and explicit reprocessing.
- Require human approval before a tool triggers an expensive GPU reprocessing job.

Verification:

- Every answer claim links to retrieved evidence and timestamps.
- Missing-evidence queries abstain rather than inventing citations.
- Retrieval metrics are reported separately from answer metrics.
- Transcript prompt injection cannot directly trigger tools or bypass permissions.
- The retrieval feature reuses the existing job, bundle, logging, and evaluation infrastructure.

**Gate G12 / partial Artifact E:** timestamped retrieval is evaluated and evidence-grounded; an agent framework is not required.

## 9. Optimized Dependency Order

```text
G0 reproducible baseline
  -> G1 isolated pipeline
    -> G2 config and lineage
      -> G3 durable API
        -> G4 asynchronous worker (Artifact C behavior)
          -> G5 Compose deployment (Artifact C local)
            -> G6 MLflow and gates
              -> G7 observability
                -> G8 CI
                  -> G9 manual AWS
                    -> G10 IaC/CD (Artifact D)
                      -> G11 Kubernetes (optional deployment skill)
                      -> G12 retrieval (optional partial Artifact E)
```

Some tasks may overlap after their contracts are stable:

- Compose image work can start while API endpoints are completed.
- Dashboard work can start once metric names are frozen.
- AWS infrastructure documentation can be drafted during CI work, but paid resources wait for G8.
- Retrieval dataset design can start after timestamp contracts exist, but implementation waits for Artifact D stability.

## 10. Testing Strategy

### Unit tests

- Pure, fast, no network, no database, no GPU.
- Configuration, prompts, normalization, manifests, output parsing, state transitions, and gate calculations.

### Integration tests

- PostgreSQL migrations and repository behavior.
- Valkey queue publication/consumption.
- Object upload/download and artifact naming.
- API-to-worker contracts using a fake model.
- MLflow logging and registry calls against the local server.

### End-to-end tests

- Compose test profile with one tiny fixture and fake inference.
- Local GPU smoke test with one real short video.
- Staging cloud smoke test after deployment.

### Benchmark tests

- Versioned representative subset for candidate gates.
- Full dataset runs only when needed.
- Warm-up and measured runs separated.
- Latency distributions, not only means.
- Quality, failure rate, throughput, and GPU memory reported together.

### Failure tests

- Invalid/corrupted/oversized video.
- Missing audio and transcript.
- Worker termination during inference.
- CUDA OOM.
- Queue/database/object-store unavailability.
- Duplicate submission.
- Timeout and retry exhaustion.
- Result upload failure.

## 11. Evaluation and Release Policy

### Required candidate identity

Every candidate is the tuple:

```text
model revision
+ processor revision
+ prompt version
+ taxonomy version
+ preprocessing version
+ runtime configuration
+ output schema version
+ container image digest
```

### Required gate dimensions

- Summary quality: BERTScore plus curated example review.
- Category quality: accuracy and weighted F1 against a valid normalized taxonomy.
- Reliability: processed count and failure rate.
- Performance: p50/p95 latency, throughput, and peak GPU memory.
- Reproducibility: complete lineage fields and retained artifacts.
- Compatibility: schema and migration checks.

Initial numerical thresholds must be derived from a trustworthy restored baseline, not invented in advance. Store thresholds in a reviewed configuration file. A gate override requires a reason and approver.

### Deployment promotion

```text
development -> candidate -> staging -> production
```

- `candidate`: benchmark completed.
- `staging`: gate passed and immutable image exists.
- `production`: staging smoke test passed and approval recorded.
- Rollback selects the prior image digest and inference-bundle version together.

## 12. Operational Metrics

### Service

- Request count, error count, and latency.
- Queue depth and oldest queued-job age.
- Jobs by state.
- Retry and timeout counts.
- Dependency readiness.

### Model

- Model load/cold-start time.
- Transcript, decode, preprocessing, generation, and post-processing latency.
- Videos/hour and generated tokens/second.
- GPU utilization and peak memory.
- OOM and decode errors.
- Model, bundle, and prompt versions.

### Data and output quality

- Video duration/resolution/size distributions.
- Missing transcript and audio rates.
- Transcript language and length distributions.
- Summary length distribution.
- Predicted category distribution.
- Offline quality metrics when labels become available.

Alert thresholds should initially be conservative and revised from observed baselines. Avoid alerting on metrics that have no owner or response procedure.

## 13. Security and Privacy Baseline

- Never accept a client-supplied local path.
- Generate object keys and temporary paths server-side.
- Enforce upload size, duration, and type limits.
- Treat video and transcript contents as untrusted data.
- Store secrets outside Git and inject them at runtime.
- Give API and worker separate IAM roles.
- Use presigned URLs with short expirations for object transfer.
- Encrypt cloud storage and databases in transit and at rest.
- Redact tokens, credentials, raw transcripts, and personal content from routine logs.
- Define artifact retention/deletion policy.
- Record who submitted, retried, cancelled, promoted, or overrode a gate.
- Require approval for costly or externally visible operations.
- Scan dependencies and container images, but keep findings actionable rather than accumulating ignored alerts.

## 14. Documentation Deliverables

- Updated README quick start.
- Architecture diagram and component responsibilities.
- Local Compose operations guide.
- API usage examples and generated OpenAPI documentation.
- Dataset manifest and taxonomy documentation.
- Experiment authoring guide.
- Evaluation-gate and registry guide.
- AWS deployment and teardown runbook.
- Cost-control checklist.
- Incident, rollback, backup, and restore runbooks.
- Kubernetes learning deployment guide, if Phase 11 is completed.
- Retrieval evaluation report, if Phase 12 is completed.
- Short ADRs for decisions whose alternatives matter.

## 15. Prioritized Backlog

### P0 — required for Artifact C

- Baseline and taxonomy stabilization.
- Reusable inference core and fake model.
- Per-video timings and failure records.
- PostgreSQL/Alembic job store.
- FastAPI job endpoints and validation.
- S3-compatible artifacts.
- Valkey/Celery asynchronous worker.
- Structured result schema and idempotency.
- Docker Compose test and GPU profiles.
- Unit/integration/end-to-end tests.
- Health, logs, metrics, and basic security.

### P1 — required for Artifact D

- Experiment configs and manifests.
- MLflow tracking and inference-bundle registry.
- Evaluation comparison and gates.
- GitHub Actions CI and container workflows.
- Manual AWS staging deployment.
- OpenTofu/Terraform-compatible infrastructure.
- Gated staging deployment and rollback.
- Cost reporting and teardown automation.

### P1 optional learning target

- Local Kubernetes deployment demonstrating probes, limits, services, ingress, jobs, and rolling updates.

### P2 — optional partial Artifact E

- Timestamped transcript generation.
- pgvector schema and embedding pipeline.
- Dense/lexical retrieval and metadata filtering.
- Citation-producing answer pipeline.
- Retrieval and groundedness evaluation.
- Only then, a narrowly justified router/tool layer.

## 16. Stop/Go Review Points

At the end of every gate, record:

- What was demonstrated.
- Test and benchmark evidence.
- New operational or economic risk.
- Actual versus expected effort.
- Whether the next phase still adds portfolio value.
- Which deferred items were explicitly rejected.

Stop or defer a phase when:

- It duplicates a capability already demonstrated.
- It adds a managed service without a concrete requirement.
- It creates permanent cloud cost before the local equivalent works.
- Its acceptance criterion cannot be tested.
- It weakens the core inference service to add a fashionable framework.

## 17. Final Definitions of Done

### Artifact C

- `docker compose up` starts the documented local system.
- Client submits a validated video job without blocking on inference.
- PostgreSQL durably tracks job and attempt state.
- Worker loads the model once, processes the job, and stores versioned artifacts.
- Client retrieves a schema-valid result.
- Failure, retry, cancellation, idempotency, logs, metrics, traces, and health behavior are tested.
- A CPU/fake profile works without GPU/model downloads; a GPU smoke profile proves real inference.

### Artifact D

- Every benchmark has code, data, model, prompt, taxonomy, config, and container lineage.
- MLflow records experiments, artifacts, and bundle versions.
- Automated gates compare a candidate with the production baseline.
- CI runs deterministic checks and builds immutable images.
- A passed candidate deploys to reproducible AWS staging through a protected workflow.
- Smoke testing and rollback are demonstrated.
- Cloud costs are bounded, observable, and removable through a tested teardown path.

### Optional partial Artifact E

- Videos are indexed as timestamped evidence chunks in pgvector.
- Retrieval is evaluated with Recall@k, MRR, hit rate, and missing-evidence cases.
- Responses include correct video/timestamp citations and abstain when evidence is absent.
- Latency and trajectory/evidence logs are recorded.
- Tool execution, if added, has timeouts, idempotency, permission boundaries, and approval for expensive GPU actions.

## 18. Immediate Next Sprint

The first sprint should contain only the work needed to pass G0 and G1:

1. Restore and document one baseline result.
2. Define the canonical category taxonomy and normalization policy.
3. Create the versioned dataset manifest and document exclusions.
4. Repair dependency/environment reproducibility.
5. Extract the inference core behind an injectable model-runner interface.
6. Add structured output and per-video timing/failure contracts.
7. Add fake-model tests for the full CLI flow.
8. Run a small real-GPU regression and record the result.

Do not begin FastAPI, Redis/Valkey, AWS, Kubernetes, Terraform/OpenTofu, or RAG work until this sprint passes its verification criteria. Those systems amplify the pipeline; they cannot compensate for an unreliable core.
