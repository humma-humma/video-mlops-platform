# Delivery evidence — 2026-10-09

## Local demo completion update — 2026-10-17

The rebuilt GPU stack accepted two real jobs and reused one model instance:
[current-image GPU smoke](gpu_service_smoke_current.json). PostgreSQL, queue
and MinIO readiness reported `ok`. The real result lineage records the pinned
500M model revision, four-frame configuration and TorchCodec decoder; the second
job recorded zero model-load time. A database-serialized limit of two
outstanding jobs was added; the [live admission burst](admission_demo.json)
accepted two concurrent real jobs, rejected a third with HTTP 429, then
accepted and completed another after the backlog drained. This is a bounded
overload demonstration, not a sustained capacity or tail-latency claim.

A [provisional policy](../configs/gates/local-demo.json) rejected an existing
measured 2.2B fewer-frame candidate for insufficient category coverage, higher
error rate and p95 latency; see the [gate decision](local_demo_gate.json).
It does not promote the distinct 500M serving model. The full local CPU suite
passed **159 tests with one expected optional skip**. All six Node UI/dashboard
behavior checks and complete manifest integrity passed. The
[controlled active-worker interruption](recovery_demo.json) also completed:
the first attempt stayed RUNNING until the configured deadline, failed with
`timeout`, then an explicit retry succeeded on attempt 2. The script restored
the original 840/900-second task limits. See the [incident note](../docs/INCIDENT_REVIEW_2026-10-17.md).
The [local release report](release_demo_20261017105931.json) now records an
executed candidate rollout and rollback to the exact prior API, dispatcher and
worker image IDs. The [candidate probe](release_candidate_20261017105931.json)
and [rollback probe](release_rollback_20261017105931.json) each completed a real
GPU job. Both the original result and the candidate result retained their
canonical hashes after rollback. The final API returned healthy readiness and
no release ID, consistent with the restored baseline. This is a local operational
exercise with a dirty source tree, not model-quality promotion or a CI-linked
immutable release. [Remote CI](ci_acceptance_2026-10-17.md) later passed CPU/UI
and fake-worker Compose checks using S3Mock; it does not replay the real GPU
release. A [connected Chrome review](browser_review_2026-10-17.md) later checked
the desktop demo, persisted job detail, lineage, operations telemetry and narrow
main-page layout. A walkthrough recording is still open.

The project-created [six-second shapes sample](../assets/portfolio/demo_shapes.mp4)
also [completed a real GPU submission](demo_shapes_probe.json) on the restored
baseline. It validates the public try-it input path, not semantic quality.

## Portfolio execution update — 2026-10-10

### Current cost and demo decision

Latest update: a read-only [operations dashboard](../docs/OPERATIONS.md) is
implemented at `/operations`, with service readiness, job/queue counts, recent
history and device-wide GPU telemetry. Live HTTP checks passed against the
existing service; all 16 job IDs were unchanged. Evidence:
[operations_acceptance.json](operations_acceptance.json). Fifteen targeted
Python tests and six Node behavior tests passed, including access enforcement,
missing GPU measurements and safe read-only rendering. Remote CI was updated
but not executed. The temporary preview was stopped after verification.

A direct cached-sample [GPU profile](gpu_profile.md) completed without an API
submission: summary 20.91 s, category 6.21 s, peak allocated 1,541.63 MiB.
Trace/operator artifacts, input hashes, configuration and environment were
recorded. This is native diagnostic evidence, not capacity or rebuilt-image
acceptance. Browser visual review remains blocked: no connected browser surfaces
were available and opening the in-app browser returned `Browser is not available`.
No screenshot or recorded walkthrough is claimed. Distributed request tracing,
durable metrics/alerts, rebuilt-image acceptance and executed release/rollback
remain open. Later text below records earlier milestones and pending states.

The owner chose the existing local GPU with no additional cloud spend. AWS
provisioning is deferred; region/authentication/budget inputs are no longer
blocking the local demo. No cloud resources were created.

The [local demo](../docs/LOCAL_DEMO.md) is implemented and available through a
loopback-only preview at `http://127.0.0.1:8080/`, forwarding to the existing
API. It supports submission, polling, results/download, recent jobs,
attempts/events, worker timings, lineage, cancellation/retry and live counters.
Fake inference is explicitly labeled. The preview was closed at the owner's
request; its start command remains documented. The page is also integrated into the
FastAPI source for the next image rebuild.

Verification: 148 CPU tests passed, one native-Transformers check skipped;
four Node/mock-DOM behavior tests passed; JavaScript syntax and diff checks
passed. A real GPU job completed through the preview, with history, attempts,
result retrieval, lineage, timings and metrics verified. Evidence:
[local_demo_acceptance.json](local_demo_acceptance.json). Browser visual QA
was unavailable because no browser surface is connected. A recorded walkthrough,
rebuilt-image acceptance, GPU profiling, complete operational dashboards/traces
and deployment rollback remain open. Remote CI was updated but not executed.

The [architecture decision](../docs/adr/0001-local-inference-demo.md) documents
the local cost choice, asynchronous serving, state ownership, warm worker and
limits of duplicate/recovery guarantees. Later work must preserve the reserved
evaluation set and avoid resuming model tuning without a release-related need.

### Earlier execution evidence

The [agreed direction](../docs/PORTFOLIO_DIRECTION.md) now governs this project:
production GPU inference infrastructure, system design and an interview-ready
demo. The existing video pipeline supplies the workload. Further classification
tuning is deferred; evaluation supports release governance.

- Deployment preflight preparation started. AWS/Terraform executables are absent
  and Docker engine access is denied to this session; the local HTTP API is
  live. Region, account/authentication and a demo spending ceiling are pending.
  See [AWS readiness](../docs/AWS_DEPLOYMENT_READINESS.md). No cloud identity,
  quota, costs or deployed resources have been verified.
- Added a bounded closed-loop HTTP load runner with input/client-source hashes,
  accepted-job journaling, timeout/failure accounting, attempt-based queue timing
  and deployed model/config lineage. Four real 500M GPU jobs completed across
  two concurrency-2 runs; final runner acceptance and eight runner tests passed.
  Together with seven existing subset/reservation tests, 15 targeted tests passed.
  See [serving evidence](serving_measurement_smoke.md) and
  [measurement runbook](../docs/SERVING_MEASUREMENTS.md).
- This is runner acceptance, not sustained capacity or SLO acceptance. The
  running worker has older source/torchvision decoding, so rebuilt-image GPU
  acceptance remains open. Full GPU profiling, cloud deployment, operational
  dashboards/traces, executed remote CI and release/rollback remain unfinished.
  The demo UI was subsequently implemented and verified as described above.

The historical evidence below is retained; later updates supersede its stated
priorities and pending statuses where explicit.

The full platform roadmap is **not complete**. Local service functionality and
experiment/gate foundations and fresh-stack acceptance are complete. Quality
calibration, live tracking/registry, and cloud delivery remain open.
This report separates code checks from deployed acceptance.

## Verified evidence

- 82 service/storage/GPU-adapter/validation/config/lineage/experiment/tracking
  contract tests passed in the service Python 3.12 environment. Tracking tests
  use an intercepted SDK; GPU-adapter tests use fake generation.
- 20 existing inference-core tests passed in the native model environment;
  the two lineage tests also passed there. There are 102 distinct passing tests
  across these environments. After the external acceptance run installed
  Alembic, the three migration tests passed independently in this session.
  The full acceptance command successfully ran all 105 collected CPU tests.
- The complete dataset manifest passed integrity verification:
  `fa6422f1f519e63fe0c3a8c9c25295640e21af9513f1111265c16e9e2b27dfc2`.
- Compose base, GPU override, and tracking profile parse successfully.
  Python compilation, PowerShell script parsing, and `git diff --check` passed.
- The new config-driven native GPU experiment completed on RTX 2080,
  Torch 2.8.0+cu126, Transformers 4.56.1, pinned 500M checkpoint. Report:
  `data/outputs/experiments/5de77349d93f450a8f5d560642f1d8c8/report.json`.
  Inference took 21.042 seconds, model load 2.194 seconds, peak allocated GPU
  memory 1,616,520,192 bytes. It had no execution failures, but its single
  category prediction did not match ground truth. Summary quality was not
  measured. This is explicitly smoke evidence, not a quality baseline.
- Previously supplied Docker acceptance passed MinIO input/result persistence,
  worker restart persistence, durable missing-input failures, and two real GPU
  jobs with warm model reuse. See the existing integration/GPU reports. Those
  runs predate the new migrations and lifecycle implementation.
- **Current local acceptance passed at 2026-10-09T17:03:46Z.**
  `local_acceptance.json` records all eight checks: CPU tests/migrations,
  manifest integrity, fake service, S3 storage, restart persistence, durable
  failure, real GPU service, and warm model reuse. Live readiness is `ok`.
  New GPU jobs `0fc910ee-ce8e-40f7-8f5c-7a7199e7b275` and
  `b109fec8-cc9f-4118-be09-4e02b0d96355` both remain SUCCEEDED. Their worker
  processing totals are 40.057 s and 12.832 s; second model load is 0 s.
  At that acceptance, live source-file hashes matched the workspace; the later
  sampling change is not yet verified in a rebuilt serving image. Older GPU job
  `1129b3f2-ad6f-4a82-a029-5e14515eeca3` remains readable and SUCCEEDED,
  independently confirming migration preservation.

## Implemented since that Docker acceptance

- Alembic upgrade/adoption of legacy jobs, lifecycle migration, and startup lock.
- Durable dispatch recovery, stale queue republication, atomic worker claims,
  generation fencing, watchdog deadlines, bounded dependency retries.
- Versioned API routes, idempotency conflicts/replays, paginated listing,
  cancellation, explicit retry, immutable attempt results and audit history.
- ffprobe media validation, size/duration limits, API keys, non-local config
  guards, process rate limiting, loopback Compose ports, non-root custom images.
- Content-free JSON events, W3C trace correlation, readiness and metrics.
- Exact source/input/config lineage, manifest integrity command, strict experiment
  configurations, immutable native GPU experiment reports.
- Deterministic quality/performance gates pinned to a reviewed baseline, with
  coverage/lineage/runtime checks and no silent baseline update or override.
- MLflow tracking/registry code and an optional persistent local tracking profile.
  Registration recomputes a gate and requires an immutable image digest.
- CPU and Compose GitHub Actions definitions; one Windows acceptance command.

## Remaining acceptance and scope

### Output diagnostics increment — 2026-10-10

Added optional token-constrained category generation, raw-generation journals
flushed before validation, explicit coverage/all-attempted accuracy and counts,
and CPU scorer calibration against self/mismatched references at layers 24/17.
The constrained strategy remains opt-in and is not enabled in serving. The
serving image now also pins/requires TorchCodec 0.7.0 rather than full-video
fallback decoding, and records the required decoder in inference lineage.

The full CPU suite passed 125 tests, including decoder-preflight rejection checks.
Real installed Transformers generation with the cached tokenizer passed; a
native 500M GPU smoke also completed, with a canonical but incorrect label.
This demonstrates the generation contract, not improved classification quality.
See [quality_diagnostics_status.json](quality_diagnostics_status.json).

The next container command is `scripts/run_quality.ps1 -Diagnostics`: it reuses
cached checkpoints, calibrates the scorer, and runs two four-video debug
experiments. This failure-selected set is not eligible for promotion. Live
scorer calibration and 2.2B constraint/invalid-JSON diagnostics are still
pending because this session cannot access Docker's engine. Rebuild/smoke the
serving GPU image separately to verify the new bounded decoder in the service.

The user then completed suite `76845c91141e43109dd9138775c8dbbc`.
[Independent review](quality_diagnostics_review.md) found layer-24 scorer
saturation and a pipeline argument-forwarding bug that prevented category
constraints from reaching generation. Generation options now use
`generate_kwargs`, verified by the real pipeline sanitizer and three observed
callback invocations in a native 500M GPU check. The full CPU suite passed
126 tests; four native decoding tests passed. New full comparison configs use
explicit layer 17, preserving old reports and metric identities. The fixed 2.2B
Docker boundary still needs the four-video diagnostic rerun, which now reuses
matching completed scorer controls. No quality approval or promotion occurred.

The fixed 2.2B diagnostic then completed as suite
`440d0c1c873d42f0bd481c99625fe557`: constrained two-pass produced 4/4 valid
results and 2/4 correct categories, while combined generation again failed 4/4.
Source/runner/config/sample/manifest hashes, journal coverage, metric arithmetic
and byte-identical scorer-control reuse were verified; service readiness is
`ok`. See [constrained_diagnostic_acceptance.json](constrained_diagnostic_acceptance.json).
The forwarding fix is accepted for this diagnostic scope. The broader command
`scripts/run_quality.ps1 -Constrained` now compares four-/two-frame constrained
two-pass generation on all 23 development videos with layer-17 scoring and
omits combined JSON. Its preparation and related recovery/configuration checks
passed 35 targeted tests (one native-Transformers test skipped in the lightweight
environment). The last full CPU suite passed 126 tests; full constrained quality
measurements subsequently completed. All 15 four-frame category errors have
now received an assistant review against transcripts, references and sampled
frames: seven clear topic/purpose errors and eight taxonomy/provenance cases.
Original accuracy remains 8/23. See
[classification_error_review.md](classification_error_review.md).
The deterministic reserved evaluation set contains 57 examples across 21
categories, disjoint from 24 locally recorded development/smoke IDs. Historical
exposure, independent annotation and missing-category coverage remain open;
this reservation is not production acceptance. Seven subset/reservation tests
passed for the review tooling. No new model run or prompt change was made.

| Area | Remaining work |
|---|---|
| New local service | Acceptance passed, including migration tests, rebuilt fake/GPU images, storage/restart/failure checks, and an older job surviving migration. |
| Reproducibility | Lock the separate serving/experiment dependency stacks and verify clean installs. Research `uv.lock` is unchanged; it is not the GPU serving environment. |
| Quality baseline | Corrected constrained comparisons completed on 23 development videos: both have zero failures; four frames classify 8/23 correctly, two frames 5/23. Keep four frames as the development reference. Category-error/factual review completed for all 15 mismatches; taxonomy adjudication, targeted improvement and trusted held-out evaluation remain open. See classification_error_review.md. |
| Gate policy | Derive numerical tolerances from that trusted baseline and commit a reviewed policy. No production policy or passing production candidate is claimed. |
| MLflow | Start tracking profile; verify logging/artifact reads and register a real passed candidate against the live registry. |
| Observability | Complete OpenTelemetry stage spans/export, Prometheus/Grafana provisioning/alerts, GPU/model/data-quality dashboards and load acceptance. Current tracing is correlation only. |
| Service scope | Batch-job API, optional Whisper fallback in the service, retention/orphan cleanup, stronger tenant identity and distributed rate limiting remain outside this local increment. |
| CI/delivery | Execute CI on GitHub; complete lint/type/security/SBOM/image publishing and protected candidate/deployment workflows. Workflow definitions are not proof of a passed remote CI run. |
| AWS | Account/region/quota/budget and identity preflight, reviewed cost/resource plan, manual deployment/smoke/rollback/teardown. AWS CLI is not available in this session. No paid resources were created. |
| IaC/CD | Per the project plan, follow successful manual AWS deployment and teardown; do not claim it from unexecuted templates. |
| Optional scope | Kubernetes and timestamp retrieval remain optional follow-up phases. |

The next development comparison is prepared in [the quality runbook](../docs/QUALITY_BENCHMARK.md).
Its fixed 23-video subset and three pinned experiment configurations were
generated and validated without downloads. Four new deterministic subset tests
passed, bringing the available suite to 109 tests; the completed service
acceptance above ran the earlier 105-test suite. The benchmark image and real
2.2B/BERTScore comparisons subsequently completed in suite
`2da0a29dd0ed47bcabf0017136eb55d8`; see
[the verified review](quality_benchmark_review.md). The user's first run built
the image and cached both snapshots, then the baseline child received SIGKILL
after seven videos. Full-video decoding of the next input would materialize
approximately 7.34 GB before copies, making host-memory exhaustion the leading
explanation. The benchmark now pins TorchCodec 0.7.0, explicitly enables frame
sampling, checks bounded decoding before VLM load, flushes per-video evidence,
releases the VLM before CPU scoring, and records cgroup counters on failure.
Four recovery tests and the existing experiment/subset tests passed (24 total).
The full local CPU suite then passed: 113 tests, including migration checks.
The installed Transformers sampler also passed two-/four-frame checks using
the long video's metadata. Real TorchCodec/container execution now completed
for all three runs, with 20, 19, and 6 valid results respectively. Original
reports, lineage, coverage, metric arithmetic, and per-video journals were
independently checked, and service readiness is `ok`. The shared
model loader changed to enable sampling; the existing service image must be
rebuilt and GPU acceptance repeated before claiming it runs this new loader.

The agent can reach local HTTP but cannot open Docker's engine named pipe
(`Access is denied`). Fresh images cannot be built or controlled from this
session. Run the following in the user's project PowerShell:

```powershell
& .\scripts\verify_local.ps1
```

It backs up an existing PostgreSQL database, installs CPU test dependencies,
runs tests and manifest checks, verifies the fake stack, then verifies GPU jobs.
It writes `reports/local_acceptance.json` only after all selected checks pass.
The user has now completed this sequence successfully; rerunning it is not
needed unless service code or configuration changes.
No volume deletion, Git commit/push, registry promotion, or cloud apply occurred.
