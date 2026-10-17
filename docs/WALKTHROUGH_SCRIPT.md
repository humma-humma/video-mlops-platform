# Two-minute local demo walkthrough

Record the loopback preview at `http://127.0.0.1:8080/` with the GPU Compose
stack running. The preview adds host GPU telemetry to `/operations`; the API
itself listens on port 8000. Use the project-created
[`demo_shapes.mp4`](../assets/portfolio/demo_shapes.mp4) so the recording can be
shared without third-party media. Its output is a functional example, not a
quality benchmark. Hide other desktop windows and credentials.

The newest persisted job opens automatically on page load. This gives a quick
read-only tour of the result and lineage before recording a fresh submission.

| Time | Screen and narration | Evidence to cite |
|---|---|---|
| 0:00–0:15 | Show the README architecture and the live demo health. Explain that the existing video model is the workload for an ML infrastructure exercise. | [README](../README.md) |
| 0:15–0:40 | Submit `demo_shapes.mp4`. Show immediate job acceptance, status, then the completed summary/category. Open the job's attempts, events, timings and pinned model/configuration lineage. | [Saved sample job](../reports/demo_shapes_probe.json) |
| 0:40–0:55 | Open `/operations`. Point out persisted job/queue counts, readiness and device-wide GPU utilization/memory. Say the GPU sample includes other desktop activity. | [Operations runbook](OPERATIONS.md) |
| 0:55–1:15 | Open the admission report: two accepted jobs, one HTTP 429 at the two-job limit, then a successful submission after drain. Distinguish a bounded burst from sustained capacity. | [Admission report](../reports/admission_demo.json) |
| 1:15–1:35 | Open the incident report and recovery timeline. The worker was killed while RUNNING; the first attempt timed out and an explicit retry succeeded. Explain the delay and the absence of exactly-once claims. | [Recovery report](../reports/recovery_demo.json), [incident note](INCIDENT_REVIEW_2026-10-17.md) |
| 1:35–1:55 | Show the rejected candidate gate, then the separate operational release/rollback report. Point out restored image IDs and unchanged result hashes. The gate is for a 2.2B experiment and does not approve the 500M serving model. | [Gate](../reports/local_demo_gate.json), [release](../reports/release_demo_20261017105931.json) |
| 1:55–2:05 | End on the evidence table and limits: single host/GPU, local images, no sustained SLO or cloud claim. | [README](../README.md) |

This script uses saved reports for the failure and release segments. Do not
repeat a destructive worker interruption merely to capture footage. Date the
recording and identify the saved runs as historical evidence. If the local API
or GPU is offline, omit live-service language and show only the saved reports.
