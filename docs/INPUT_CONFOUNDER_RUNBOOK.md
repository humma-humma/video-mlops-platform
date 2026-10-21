# Frozen CPU-input challenge (live result)

The [protocol](../reports/diagnostics/input-confounder-live/protocol.json) and [two-case manifest](../reports/diagnostics/input-confounder-live/cases.json) were committed before collection. They froze the diagnostic rules hash and expected labels. The first case replaced only a newly queued synthetic text job's input bytes with invalid UTF-8. The second temporarily removed a different new CPU job's input object. This is a live confounder for the packaged-model failure, which has a distinct `model_artifact_unavailable` code.

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

The first live run stopped at an overstrict evidence assertion **after restoration**. [Restoration state](../reports/diagnostics/input-confounder-live/run_state.json) confirmed both objects were restored byte-for-byte and the CPU worker was started. `scripts.recover_input_confounder_incident` matched the saved hashes to those exact failed jobs, exported their redacted evidence without rerunning the faults, and submitted a successful new control job. The [evaluation](../reports/diagnostics/input-confounder-live/evaluation.json) is **2/2 on the registered diagnoses**: one correct abstention for unreadable input, one cited missing-input finding, zero false-confidence cases. The [ledger](../reports/diagnostics/input-confounder-live/ledger.json) also records **one preregistered attempt-code miss**: unreadable UTF-8 was reported as `invalid_output` at `inference`, rather than the expected `internal` at `inference`. The missing-input code and both failure stages matched. We have not edited the protocol or frozen rules to conceal the miss. `UnicodeDecodeError` is a `ValueError`, which explains the current service's broad `invalid_output` classification; this code is misleading for an input-decoding fault and is a future taxonomy fix.

The experiment is **held out from the frozen rules** but is still one controlled local setup with known labels, not a population estimate. The unreadable-input case is a new live failure mechanism; the redacted bundle supports only `invalid_output`/`inference` and an abstention, not the exact injected bytes. The missing-input case exercises an existing rule on a second deployment. Report supported diagnoses, correct abstentions, citations, false confidence and the attempt-code miss separately.
