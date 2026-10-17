# Local operations and profiling

Start the existing loopback preview, then open `http://127.0.0.1:8080/operations`:

```powershell
& .\.venv\Scripts\python.exe -m scripts.demo_server --port 8080
```

The dashboard performs GET requests only. It polls readiness, persisted job
counts, oldest queue age, recent jobs and device-wide NVIDIA telemetry every
five seconds. Pause stops automatic polling. Enter the API key if required;
the page retains it only in memory. GPU collection first checks access against
the upstream job endpoint. No new inference job is needed. Open an existing job
in the main demo to see stage timings, attempts, events and model/config lineage.
Stop the preview with Ctrl+C when finished.

GPU samples include all applications on the device. They are not per-worker
utilization or model allocations. The chart displays the first GPU and retains
60 samples in page memory; missing samples are gaps. It has no durable time-series
store or alerts. Host telemetry is available through the local preview; the API
image may serve the dashboard without that host-only endpoint. Missing telemetry
is explicitly unavailable, never zero. Job states are historical persisted counts,
not a recent error rate. HTTP counters reset on API restart; duration sum/count
cannot establish p95. This is a lightweight local operations dashboard; distributed
request traces, durable metrics storage and alerting remain future work.

## Direct sample profile

Use the existing native CUDA environment with the checkpoint already cached:

```powershell
& 'C:\Users\mopu01\AppData\Local\anaconda3\envs\mardm\python.exe' -m scripts.profile_gpu `
  --video data/inputs/videos/7203774185322188037.mp4 `
  --transcript data/inputs/audio_transcripts/7203774185322188037.txt
```

This invokes the pinned 500M checkpoint directly, with four sampled frames, KV
cache, one two-pass warmup and one measured two-pass run. Offline mode prevents
model downloads. It does not submit, cancel, retry or restart API jobs. A GET-only
check refuses an active service queue and records job IDs before/after; this
check is not a lock against another client submitting work. If API authentication
is enabled, provide `VIDEO_API_KEY` in the process environment.

The output directory `data/outputs/gpu-profile/` contains the report, operator
table and a Chrome-format trace from [PyTorch Profiler](https://docs.pytorch.org/docs/stable/profiler).
Timings synchronize CUDA at stage boundaries. Peak allocated/reserved memory is
local to this profiling process; host samples are device-wide. Profile overhead,
other GPU applications, and a single input prevent interpreting this as capacity
or SLO acceptance. This native torchvision-fallback run does not verify the
rebuilt TorchCodec worker. It does not change evaluation labels or quality scores.
Trace files can be large and include input file paths; keep them local. Do not
commit raw traces. Profiler operator traces are distinct from distributed request
tracing across API, queue and worker.

## Current verification

See [operations acceptance](../reports/operations_acceptance.json) for live
GET-only checks against the API, unchanged job count, health and GPU samples.
Python tests cover malformed/unavailable GPU data and upstream authorization;
Node mock-DOM tests cover safe rendering, read-only polling and unavailable data.
Browser surfaces were unavailable in this session, so layout, screenshots and
interactive browser acceptance remain unverified.
