# Serving measurements

Measure the service as a system, independently of the model-quality benchmark.
The existing video/transcript pair is a repeatable workload; this is not a
representative traffic distribution or a quality acceptance set.

## Bounded HTTP runner

With the local stack already running:

```powershell
& .\.venv\Scripts\python.exe -m scripts.serving_load `
  --video data/inputs/videos/7203774185322188037.mp4 `
  --transcript data/inputs/audio_transcripts/7203774185322188037.txt `
  --jobs 2 --concurrency 2 --timeout 180
```

The runner uses `/api/v1/jobs`, polling and attempt history. It submits at most
20 jobs, bounds client concurrency and per-job observation time, and supplies
a unique idempotency key per request. Use `VIDEO_API_KEY` from the environment
for authenticated deployments; do not put credentials in the URL or command.
`--base-url` selects another deployment. Remote runs upload the supplied video
and transcript to that deployment.

Each run gets a new directory under `data/outputs/serving-load/`:

- `jobs.jsonl`: flushed accepted IDs and final observations, retained even if
  a later request fails. No generation text or authentication key is recorded.
- `report.json`: input/client-source hashes, run settings, per-job model/config
  lineage, worker stage timings, attempt evidence and aggregate measurements.

The command exits nonzero if any job fails, is cancelled, times out or has a
client error. A client timeout is **not** proof of a failed server job. Inspect
the recorded job ID before retrying; the runner does not cancel or clean up
jobs. Each run creates actual durable service jobs and artifacts.

| Measurement | Definition and limitation |
|---|---|
| Submission time | Client POST start to accepted response; includes upload, validation and persistence. |
| Observed completion time | Client POST start to observing a terminal status; includes polling delay. |
| Initial queue time | First attempt start minus server job creation; includes dispatch overhead, excludes client upload before creation. |
| Successful jobs/minute | Successful completions divided by entire measured client-run duration; failures remain in the time denominator. |
| Worker timings | Values reported by the deployed worker, not independently reconstructed timings. |
| P50/P95 | Linear interpolation over successful jobs only; counts and failures are reported separately. Tiny runs are functional checks, not tail-latency estimates. |

This is closed-loop load: each client waits for completion before its next
submission. It does not establish behavior under an independent arrival rate,
and does not replace an open-loop overload/backpressure test. It does not force
a cold start, sample GPU utilization, measure cloud cost, or promote a release.
Fake worker results remain explicitly identifiable by `model_version`; do not
present them as GPU measurements.

## Next measurement acceptance

1. Verify rebuilt GPU image and record its digest/configuration first.
2. Record cold execution separately using a controlled worker restart; record
   process startup/checkpoint loading separately from request execution.
3. Run controlled warm workloads at client concurrency 1, 2 and 4 with sample
   sizes justified by runtime/cost. Keep workload, hardware and image fixed.
4. Collect host and GPU utilization/memory alongside queue age, job errors and
   stage traces. GPU allocated bytes and device memory used are different
   measurements. Separate decode/preprocess from model execution where the
   runtime permits it; do not rename total generation time as pure GPU time.
5. Compare batching/concurrency alternatives only after profiling identifies
   the bottleneck. Report rejected alternatives and capacity limits.
6. Test bounded overload and recovery separately, preserving failed and timed
   out requests in the evidence. Set a workload-specific SLO from measured
   behavior and demo requirements, not a guessed passing number.

Record installed/deployed versions and distinguish an old running image from
current workspace source. A repeated-input two-job run validates the runner;
it does not close the capacity/profiling milestone.
