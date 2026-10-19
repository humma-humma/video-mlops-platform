# Prospective result-object loss incident

The [protocol](../reports/diagnostics/result-loss-live/protocol.json) and [case label](../reports/diagnostics/result-loss-live/cases.json) were committed as `edbe7c3` **before** collection. They specified one new synthetic CPU job, deletion of only that job's result object, a read failure while the durable job record stayed successful, exact object restoration, and an expected `insufficient_evidence` diagnosis. No GPU job or user artifact was involved.

The [live ledger](../reports/diagnostics/result-loss-live/ledger.json) records a 202 submission, one successful attempt, and a successful result read. The script retained the object's original bytes in memory, deleted the result object, then observed HTTP 503 from the job read while the job list still reported `SUCCEEDED` and the MinIO bucket remained available. Its `finally` block restored the exact bytes; the API then returned the original result with HTTP 200. The [restoration record](../reports/diagnostics/result-loss-live/run_state.json) confirms the byte hash. The [incident index](../reports/diagnostics/result-loss-live/incident.json) links the protocol, ledger, restoration record and redacted [bundle](../reports/diagnostics/result-loss-live/missing_result.json) by SHA-256. The service's readiness endpoint was healthy afterward.

The unchanged baseline saw a successful job record and a 503 result read, but has no rule that can attribute that 503 to object deletion. It abstained as pre-registered: [1/1 correct abstention, zero false-confident diagnoses](../reports/diagnostics/result-loss-live/evaluation.json). The external intervention ledger establishes the injected mechanism; the analyzer does **not** infer it from the bundle. This is one controlled local failure, distinct from the earlier whole-MinIO outage during input checking. It is not an estimate of diagnosis accuracy on naturally occurring incidents.

Verify the saved evidence offline:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider tests/test_result_loss_incident.py
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench evaluate `
  --cases reports/diagnostics/result-loss-live/cases.json `
  --output reports/diagnostics/result-loss-live/evaluation.json
```

The live script refuses to overwrite the recorded incident. A new run needs a fresh output directory with copies of `protocol.json` and `cases.json`. It manipulates only its newly created job's result and restores it automatically; it should be run only against the local demo's MinIO endpoint.
