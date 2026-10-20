# Diagnostic case index

Start with the [40-second recorded-evidence walkthrough](../assets/portfolio/diagnostic_walkthrough.mp4), then inspect the linked bundles and evaluations. The walkthrough is a rendered, silent explanation of saved reports, **not** footage of a live browser session. The [workbench guide](DIAGNOSTIC_WORKBENCH.md) gives the offline commands and evidence boundary.

| Collection | Mechanism tested | Diagnostic result | Evidence limit |
| --- | --- | --- | --- |
| [Frozen mixed set](DIAGNOSTIC_MIXED_SET.md) | 12 retrospective cases from seven collections | 4 supported findings; 8 abstentions | Cases influenced rule development; not independent accuracy |
| [MinIO interruption](MINIO_INCIDENT_RUNBOOK.md) | Local artifact check fails, retry later succeeds | Cited failure stage/code | Does not identify MinIO from the bundle alone |
| [Damaged video](DECODER_INCIDENT_RUNBOOK.md) | Real GPU worker and typed frame-preflight failure | Cited `decode_failed` after repair | Cannot name underlying codec/data defect |
| [Admission burst](../reports/diagnostics/admission-live-v2/incident.json) | GPU capacity reached and later drained | Cited capacity limit and negative-control abstention | Short local burst, not sustained throughput |
| [Rate-limit replay](LIVE_RATE_LIMIT_RUNBOOK.md) | Request middleware emits 429 without GPU saturation | Abstention | Repeats a known isolated mechanism |
| [Unrelated worker](UNRELATED_WORKER_RUNBOOK.md) | CPU worker interrupted during successful GPU job | Abstention | External kill event is script-recorded |
| [Result object loss](RESULT_LOSS_RUNBOOK.md) | One completed job's result object disappears | Abstention; exact result restored | Bundle cannot infer object deletion |
| [Model artifact loss](MODEL_ARTIFACT_INCIDENT_RUNBOOK.md) | Packaged CPU model unavailable; control succeeds after restoration | Cited typed code, 1/1 development | Rule built for this mechanism |
| [New CPU-input challenge](INPUT_CONFOUNDER_RUNBOOK.md) | Undecodable bytes versus missing input object | Pre-registered; live run pending | Frozen rules, two related synthetic jobs |

The [proposal and replay](../reports/diagnostics/proposals/model_artifact_build_gate.json) uses the model-artifact incident to suggest a build-time artifact gate. Its patch remains unapplied and requires human review. Score supported findings, correct abstentions, citation accuracy and false confidence separately; do not sum all passes into a root-cause accuracy percentage.
