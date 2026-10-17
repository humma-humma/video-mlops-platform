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

The baseline reports `worker_interruption` only when a recorded worker kill precedes a timed-out attempt. It reports `gpu_admission_limit` when the recorded number of accepted jobs reaches recorded capacity and another submission receives 429. Otherwise it returns `insufficient_evidence`. Each non-abstaining result cites exact paths in the bundle. A 429 alone is not enough to prove GPU saturation, and a timeout alone is not enough to blame a worker kill.

The next useful experiment is to collect **independent** incidents with genuine confounders: a decoder/preprocessing slowdown, storage fault, rate-limit 429, memory pressure and an unrelated worker restart. Freeze a held-out set before changing the rules. Score cause identification, citation correctness, false confidence and abstention separately. Only then consider configuration proposals or an agent challenger. The agent would consume these bounded bundles and propose a reviewable diff; it would not receive production mutation rights or shell access. The [feasibility analysis](DIAGNOSTIC_WORKBENCH_FEASIBILITY.md) explains the larger scope and kill criterion.

## Current limits

The API exporter was exercised against the running loopback service, but Docker engine access remains unavailable in this session; no new deployment or failure injection was run. The existing two incident reports were captured before this bundle format existed. Their hashes establish provenance of the source files used by the builder; they do not independently authenticate the original collection. The baseline covers two narrow failure patterns and cannot explain every failed job. No external cluster, SLURM environment, distributed tracing, agent, replay deployment or production access is claimed.
