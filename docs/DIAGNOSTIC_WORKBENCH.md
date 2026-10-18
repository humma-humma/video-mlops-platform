# Offline diagnostic workbench pilot

This is the first, bounded slice of the [restricted-access diagnostic workbench plan](PORTFOLIO_REFERENCE.md#10-future-product-idea-restricted-access-inference-diagnostics). It collects an allowlisted evidence bundle without changing a job, then runs deterministic checks against that bundle offline. It is a diagnostic aid and evaluation harness, not an agent or a production root-cause system.

## Try it without a running service

From the project PowerShell with the service `.venv`:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.build_diagnostic_cases
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench analyze --bundle reports/diagnostics/pilot/recorded_worker_interruption.json
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench evaluate --cases reports/diagnostics/pilot/cases.json --output reports/diagnostics/pilot/evaluation.json
```

The source reports are the [controlled worker interruption](../reports/recovery_demo.json) and [GPU admission burst](../reports/admission_demo.json). The builder exports sanitized versions and six explicitly labeled synthetic variants. The [pilot evaluation](../reports/diagnostics/pilot/evaluation.json) matches all eight labels and verifies that its citations resolve to bundle fields. The two parent incidents were observed locally; variants are edited copies, **not additional real incidents**. The development/held-out split prevents the evaluator from reading labels at inference time, but these variants share their parent reports and were designed with the rules. The 8/8 figure only shows the initial contract works; it is not a meaningful estimate of diagnosis accuracy on independent incidents.

### Historical live-job challenge

The [observed-case manifest](../reports/diagnostics/observed/cases.json) adds four distinct historical failed jobs exported from the local API on 2026-10-18. These are actual job records, not variants of the two pilot reports. One failed attempt explicitly reports `missing_input`; one text-deployment failure reports only `internal`; two older service-smoke failures retain a failed job status but no attempt or event history through the current API. The last two are related controlled checks, so four jobs do **not** imply four independent failure mechanisms. The exported [evaluation](../reports/diagnostics/observed/evaluation.json) matches 4/4 evidence-level labels, with three abstentions and no false-confident diagnoses. The missing-input case is development data: we added its rule after inspecting it. The other three are held out from that rule, but this small local collection is not a generalization benchmark.

Run the frozen cases offline without starting Docker or submitting a video:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench evaluate --cases reports/diagnostics/observed/cases.json --output reports/diagnostics/observed/evaluation.json
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench analyze --bundle reports/diagnostics/observed/text_failure.json
```

`reported_missing_input` means the service recorded that exact code on a failed attempt; it does not prove who deleted an artifact or why it was unavailable. `internal` identifies only a generic failure, so the workbench abstains. The current capacity and release fields in these historical bundles were collected days later; they cannot explain the old jobs. Source-response hashes identify what the exporter read, but the original API records are not independently signed. No raw job IDs, error messages, user content or credentials are stored in the bundles.

### Controlled service-task challenge

The [offline walkthrough](DIAGNOSTIC_WALKTHROUGH.md) reproduces storage read/write failures and stage-specific slowdowns through the real worker task with a simulated adapter. The [case manifest](../reports/diagnostics/challenge/cases.json) was fixed before the recorded run; its two development and four challenge cases are all from the same hand-designed harness. The [evaluation](../reports/diagnostics/challenge/evaluation.json) matches 6/6 evidence-level labels and abstains on an adapter dependency fault and a mixed-stage slowdown. These labels identify a recorded failure stage or measured latency regression, **not a downstream root cause**. No GPU model or MinIO is exercised. The replay captures an allowlisted `failure_stage` from a structured worker event; the live API exporter cannot currently provide that field.

To export one existing job from the running service without submitting or retrying work:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench export-job --job-id <job-uuid> --output reports/diagnostics/my-job.json
```

Set `VIDEO_API_KEY` in the shell if the service requires it. The collector accepts only a loopback HTTP API, disables proxying and redirects, makes five GET requests (`job`, `attempts`, `events`, current liveness and current metrics), uses a 10-second request timeout, and limits each response to 2 MB and each history to 100 records. It does not need Docker control, database credentials, object-store credentials or write permission to the service. An offline report can be converted with `export-report --source reports/recovery_demo.json --output <path>`.

A [live read-only check](../reports/diagnostics/live_acceptance_2026-10-18.md) exported an existing CPU job and an existing recovery job. The API-only recovery bundle abstains because the external worker-kill event is absent; the separately recorded recovery report supplies that evidence. No new inference job was submitted for this check.

To inspect a stage-timing difference between two exported jobs from the **same deployment and input bytes**:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench compare --baseline reports/diagnostics/live_gpu_cold.json --candidate reports/diagnostics/live_gpu_warm.json --output reports/diagnostics/live_gpu_comparison.json
```

The [recorded comparison](../reports/diagnostics/live_gpu_comparison.json) uses two existing GPU jobs with matching input, deployment, model revision and lineage hashes. It shows a first-job model-load time of about 32 seconds and zero repeated model-load time on the warm job. It reports differences without asserting that all of the total-time change was caused by caching; host and GPU conditions were not controlled for a causal benchmark. Cross-deployment or different-input comparisons are rejected.

The bundle includes status, bounded attempt/event history, known error codes, stage timings, input/model/configuration hashes and limited current capacity metrics when available. The current release identity is hashed and explicitly labeled as a **collection-time snapshot**, because it may differ from the image that produced an old job. Source-response SHA-256 values and a canonical bundle hash make corruption detectable. The importer checks the schema, allowlisted fields and integrity hash before analysis. Video bytes, transcripts, generated summaries, raw result text, free-form errors, trace IDs, job IDs, API keys and unknown metric labels are excluded. Missing raw logs, per-job GPU telemetry, producer release identity and external worker-lifecycle events are identified instead of invented. Redaction is an allowlist for this schema; treat new fields as untrusted until reviewed.

## Diagnostic rules and evaluation boundary

The baseline reports `worker_interruption` only when a recorded worker kill precedes a timed-out attempt. It reports `gpu_admission_limit` when the recorded number of accepted jobs reaches recorded capacity and another submission receives 429. It reports `reported_missing_input` when a failed job has a failed attempt with that exact service error code. A new `reported_decode_failure` rule requires the repaired worker's typed `decode_failed` attempt code; generic `inference`, `decode_timeout` and `decoder_unavailable` still abstain. For isolated replay bundles, it separates two `dependency` failures only when a structured worker event supplies the failure stage. A pairwise rule identifies a **measured** preparation or download latency regression only for successful runs with matching input, model and lineage, a material total-time increase and a dominant stage delta. Otherwise it returns `insufficient_evidence`. Each non-abstaining result cites exact paths in the bundle. A 429 alone is not enough to prove GPU saturation, and a timeout alone is not enough to blame a worker kill.

The [live MinIO interruption runbook](MINIO_INCIDENT_RUNBOOK.md) reproduces one real local storage failure. On 2026-10-18, a CPU text job failed while MinIO was stopped, with a durable `dependency` attempt and a job-correlated `artifact_check` worker event. After MinIO restarted, an explicit retry succeeded and retained input lineage. The [incident ledger](../reports/diagnostics/minio-live/incident.json), [failed](../reports/diagnostics/minio-live/failed_job.json) and [recovered](../reports/diagnostics/minio-live/recovered_job.json) bundles and [restoration state](../reports/diagnostics/minio-live/run_state.json) record those observations. The [single-case evaluation](../reports/diagnostics/minio-live/evaluation.json) matches its pre-specified evidence-level label and resolves both citations (1/1); it is an acceptance check, not an independent accuracy estimate. The analyzer reads the failed bundle, not the outage ledger, and therefore reports only the stage and code; it does not claim to identify MinIO from those fields alone.

The [damaged-video runbook](DECODER_INCIDENT_RUNBOOK.md) records a second real local experiment. A synthetic MP4 passed metadata inspection but failed full FFmpeg decoding; the real GPU job recorded a generic `inference` failure. A known video succeeded as a service control. The workbench abstained because the exported job did not identify a decoder-specific worker exception, and it refused a latency comparison between different inputs. An intact synthetic test pattern also produced an `inference` failure, showing why that code alone cannot establish a decoder cause. The [two-case evaluation](../reports/diagnostics/decoder-live/evaluation.json) checks both abstentions, not accuracy on independent incidents.

The first-frame repair is implemented in source but awaits a rebuilt GPU worker and [v2 live acceptance](DECODER_INCIDENT_RUNBOOK.md#repair-and-acceptance). The earlier incident remains historical evidence of the observability gap; its exported attempts are not rewritten to carry the new code.

The next useful experiment is to capture other **real local** failure mechanisms with genuine confounders: a preprocessing slowdown, rate-limit 429, memory pressure and an unrelated worker restart. Freeze an independently collected set before changing the rules. Score cause identification, citation correctness, false confidence and abstention separately. The controlled replay, live outage and damaged-video run do not satisfy the plan's independent-incident requirement. Only then consider configuration proposals or an agent challenger. The agent would consume these bounded bundles and propose a reviewable diff; it would not receive production mutation rights or shell access. The [feasibility analysis](DIAGNOSTIC_WORKBENCH_FEASIBILITY.md) explains the larger scope and kill criterion.

## Current limits

The API exporter was exercised against the running loopback service. The MinIO interruption was executed from the project PowerShell because Docker engine control is unavailable to this agent session; its saved reports were validated offline afterward. The earlier two incident reports were captured before this bundle format existed. Their hashes establish provenance of the source files used by the builder; they do not independently authenticate the original collection. The baseline covers narrow failure patterns and cannot explain every failed job. No external cluster, SLURM environment, distributed tracing, agent, replay deployment or production access is claimed.
