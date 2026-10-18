# Offline incident walkthrough

This five-minute walkthrough runs entirely on a developer machine. It exercises the real `process_job` claim, attempt, event, artifact and failure paths with in-memory SQLite, local filesystem storage and a simulated video adapter. It submits no job to the running demo and uses no GPU, Docker, S3 or user video. The [injection ledger](../reports/diagnostics/challenge/injection_ledger.json) records the requested delays and fault locations separately from the analyzer's bundles.

From the repository root, install `requirements-service-test.txt` in the project `.venv` if needed, then run:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.build_diagnostic_challenge
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench analyze --bundle reports/diagnostics/challenge/storage_read_fault.json
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench analyze --bundle reports/diagnostics/challenge/storage_write_fault.json
```

Both failures have service error code `dependency`. The first bundle also has a structured worker event placing failure at `input_download`; the second places it at `result_storage`. The analyzer reports different **observed failure stages**, with citations to the stage and attempt code. It does not infer whether the underlying cause was MinIO, credentials, a network interruption or something else. Inspect `dependency_inside_adapter.json`: it has the same code at `inference`, for which the rule abstains.

Now compare a baseline with the two latency cases:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench analyze-pair --baseline reports/diagnostics/challenge/baseline.json --candidate reports/diagnostics/challenge/preparation_delay.json
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench analyze-pair --baseline reports/diagnostics/challenge/baseline.json --candidate reports/diagnostics/challenge/download_delay.json
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench analyze-pair --baseline reports/diagnostics/challenge/baseline.json --candidate reports/diagnostics/challenge/mixed_delay.json
```

All pairs use the same fixture bytes, deployment, model revision and lineage hashes. The first reports a dominant `input_preparation` time increase; the second reports a dominant `input_download` increase, even though both have higher total time. The mixed case increases both stages and should abstain. Timings vary by machine; the diagnosis depends on measured deltas, not the requested sleep values in the ledger. The adapter only sleeps to simulate a preprocessing stage: this is **not evidence of a real decoder regression**.

Score the [frozen case manifest](../reports/diagnostics/challenge/cases.json):

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench evaluate --cases reports/diagnostics/challenge/cases.json --output reports/diagnostics/challenge/evaluation.json
```

The [recorded run](../reports/diagnostics/challenge/evaluation.json) matches 6/6 evidence-level labels, has valid field citations and abstains twice. Two cases were used to develop the rules; four are challenge cases from the same hand-designed harness. This is a reproducibility and abstention check, not an estimate of accuracy on independent incidents. The collector does not yet join structured worker failure events to a live API job, so stage-specific diagnoses here are limited to the isolated replay bundles. Actual GPU contention, decoder behavior and MinIO outages remain untested by this challenge.
