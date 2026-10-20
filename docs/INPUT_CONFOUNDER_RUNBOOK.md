# Frozen CPU-input challenge (pending live run)

The [protocol](../reports/diagnostics/input-confounder-live/protocol.json) and [two-case manifest](../reports/diagnostics/input-confounder-live/cases.json) were committed before collection. They freeze the diagnostic rules hash and expected labels. The first case replaces only a newly queued synthetic text job's input bytes with invalid UTF-8; the service currently records a generic `internal` failure at `inference`, so the unchanged analyzer should abstain. The second temporarily removes a different new CPU job's input object; its attempt should record `missing_input` at `artifact_check` and receive a cited `reported_missing_input` diagnosis. The latter is a live confounder for the packaged-model failure, which must retain its distinct `model_artifact_unavailable` code.

The code also adds migration `0004`, which persists an allowlisted failure stage in the attempt history. Historical attempts remain nullable, and older bundles retain their hashes. Only one failed attempt's stage is exported into a live diagnostic bundle; unknown stages are dropped. No free-form error text or input bytes enter the bundle.

From the project PowerShell with the existing MinIO-backed Compose stack and no outstanding CPU jobs:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml build migrate api cpu-worker
docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm migrate
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d api cpu-worker
& '.\.venv\Scripts\python.exe' -m scripts.input_confounder_incident
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench evaluate `
  --cases reports/diagnostics/input-confounder-live/cases.json `
  --output reports/diagnostics/input-confounder-live/evaluation.json
```

The runner refuses an unready API, existing CPU backlog, changed rules hash or existing evidence. It stops only the CPU worker, submits two new synthetic jobs, verifies their S3 objects, injects the two faults, and starts the same worker container. A `finally` block restores both original objects and starts the worker if necessary. It records restoration status even if an assertion fails. After restoration, it submits a third control job and requires success. It never deletes volumes, changes the GPU worker or modifies an existing user's job.

The experiment is **held out from the frozen rules** but is still one controlled local setup with known labels, not a population estimate. The unreadable-input case is a new live failure mechanism whose exact injected bytes are documented only in the external ledger; the redacted bundle supports only the weaker `internal`/`inference` observation and an abstention. The missing-input case exercises an existing rule on a second deployment. Report supported diagnoses, correct abstentions, citations and false confidence separately.
