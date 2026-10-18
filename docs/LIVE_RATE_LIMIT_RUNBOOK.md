# Prospective deployed API rate-limit incident

The [protocol](../reports/diagnostics/rate-limit-live/protocol.json) and [case label](../reports/diagnostics/rate-limit-live/cases.json) were committed as `7c6e372` before collection. They specified a read-only `/openapi.json` probe, a 650-request and 45-second bound, recovery within 75 seconds, zero GPU jobs outstanding before and after, and an expected `insufficient_evidence` diagnosis. The probe ran against the existing local API on 2026-10-19 without submitting, retrying or changing a job.

The [ledger](../reports/diagnostics/rate-limit-live/ledger.json) records 599 HTTP 200 responses followed by one 429 with the API middleware's fixed rate-limit response and `Retry-After: 60`. `/health/live` remained available during the limit; `/openapi.json` recovered to 200. GPU outstanding jobs were zero and recorded capacity was two before and after. The API release hash was unchanged. The [incident index](../reports/diagnostics/rate-limit-live/incident.json) links the protocol, ledger and redacted [bundle](../reports/diagnostics/rate-limit-live/rate_limit.json) by SHA-256.

The bundle deliberately retains only the ambiguous 429, with no accepted GPU-job sequence or rate-limit response body. The unchanged deterministic rules therefore abstained, matching the pre-registered label in the [evaluation](../reports/diagnostics/rate-limit-live/evaluation.json): **1/1 correct abstentions, zero false-confident diagnoses**. The ledger establishes that this particular 429 came from request-rate middleware; the analyzer cannot infer that from the narrower bundle. This is a prospective **deployment-level repeat of a known mechanism** already exercised in an isolated middleware control, not an independent failure family or an estimate of generalization.

Verify the saved evidence offline without making requests:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider tests/test_live_rate_limit_incident.py
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench evaluate `
  --cases reports/diagnostics/rate-limit-live/cases.json `
  --output reports/diagnostics/rate-limit-live/evaluation.json
```

The live script refuses to overwrite this evidence. For a fresh run, create a new output directory containing copies of `protocol.json` and `cases.json`, then pass that directory with `--output-dir`. Running the probe briefly consumes the local API's request-rate budget; it does not need Docker control or a GPU. The next stronger challenge should pre-register a genuinely different failure mechanism, such as a measured preprocessing slowdown, before collection.
