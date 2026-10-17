# Serving measurement runner acceptance ? 2026-10-10

The bounded HTTP runner completed **four real GPU jobs** over two two-job runs
at client concurrency 2. Both runs had zero failed jobs, cancellations, client
errors or timeouts. All jobs reused the same deployed model instance.

| Observation | First run | Second run |
|---|---:|---:|
| Successful jobs | 2/2 | 2/2 |
| Client run elapsed | 75.11 s | 34.13 s |
| Observed completions/minute | 1.60 | 3.52 |

The first job reported 27.35 s of model loading; subsequent jobs reported zero.
The second job in the first run waited 53.44 s from server job creation to its
first attempt, illustrating queueing behind a single warm-model worker. The
first run did not force a restart; this is an observed cold load, not controlled
cold-start acceptance. Differences between these tiny runs are not proof of
sustained capacity or an optimization gain. Percentiles in raw reports have
only two observations and must not be presented as production tail latency.

The deployed service uses the pinned SmolVLM2-500M model and reports the older
torchvision decoder. Its source lineage differs from the current workspace;
rebuilt GPU-image acceptance remains required. This is service-level evidence,
not the 2.2B quality benchmark and not verification of the latest loader.

The client runner was improved after the first run to label accepted journal
events as ACCEPTED and automatically archive its source before execution.
Both original reports remain untouched; source snapshots match their recorded
hashes. The second run verifies the final runner. Fifteen targeted tests passed,
including eight runner tests. Default Windows temporary-directory access failed
for one existing test; rerunning with the established workspace fixture passed.

See [serving_measurement_smoke.json](serving_measurement_smoke.json) for hashes,
job IDs, stage timings and exact source differences, and
[SERVING_MEASUREMENTS.md](../docs/SERVING_MEASUREMENTS.md) for reproduction and
measurement definitions. No cloud resources, model changes, promotion or
worker restarts were performed.
