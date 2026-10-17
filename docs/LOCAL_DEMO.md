# Local portfolio demo

The active route uses the existing PC/GPU and adds **no cloud-hosting charges**.
Electricity and existing hardware are still costs. AWS provisioning is deferred;
the project does not claim executed cloud deployment evidence.

## Start and open

With the local GPU API stack already running on port 8000:

```powershell
& .\.venv\Scripts\python.exe -m scripts.demo_server --port 8080
```

Open **http://127.0.0.1:8080/** in a modern browser. The preview serves current
workspace assets and forwards only known API routes to `127.0.0.1:8000`. It
binds to loopback; it is not a public hosting solution. Stop it with Ctrl+C in
its terminal. The optional `--api-url` accepts another loopback HTTP origin.

The UI is integrated at `/` in the FastAPI service. The preview is optional
when developing page assets without rebuilding the container; it does not
change the deployed API or worker image. The rebuilt GPU image has separate
[acceptance evidence](../reports/gpu_service_smoke_current.json).

If the stack is not running, follow [GPU setup](GPU_WORKER_LOCAL.md). Review
the existing acceptance instructions before rebuilding or switching between
fake and real workers.

## Five-minute walkthrough

1. Show service health: PostgreSQL, queue/worker and artifact-store checks.
2. Choose a small MP4. For the repeatable local example, use
   `data/inputs/videos/7203774185322188037.mp4` and paste its corresponding
   `data/inputs/audio_transcripts/7203774185322188037.txt` transcript.
   For a redistributable functional sample, use the project-created
   [`demo_shapes.mp4`](../assets/portfolio/demo_shapes.mp4) without a transcript.
   It is a six-second two-scene geometric clip generated entirely with FFmpeg;
   it tests submission and decoding, not model accuracy or a meaningful category.
   It contains no third-party video, audio or images. Recreate it from the
   repository root with:

   ```powershell
   ffmpeg -y -f lavfi -i 'color=c=0x0b3954:s=640x360:r=12:d=6' -vf "drawbox=x=80:y=90:w=140:h=140:color=0xffb703:t=fill:enable='lt(t,3)',drawbox=x=400:y=100:w=120:h=120:color=0xfb8500:t=fill:enable='gte(t,3)'" -c:v mpeg4 -q:v 5 -pix_fmt yuv420p assets/portfolio/demo_shapes.mp4
   ```
3. Submit the job and explain why HTTP acceptance returns before GPU execution.
   Follow QUEUED/RUNNING to its terminal status. Reload the page and select the
   job from Recent jobs to demonstrate that state belongs to the service.
4. Inspect the summary/category, download the result JSON, then open attempts,
   events, trace correlation and model/config lineage. Fake results display
   **SIMULATED**; never present them as real inference.
5. Explain worker timings and model reuse. A cold model load is reported only
   when actually observed; a warm result does not prove process cold-start time.
6. Open the [operations dashboard](OPERATIONS.md) at `/operations` for readiness,
   queue/job counts, recent history and host GPU activity. It can be reviewed
   without submitting a video. Explain device-wide measurements and the measured
   single-GPU queueing limit; distributed request tracing remains open.

The UI limits videos to 64 MiB and stores no API key in browser storage. If
authentication is enabled, enter the key and press Refresh. It remains in the
page's memory only. Optional transcripts are sent to the local service and
persisted there. Do not use confidential media for a public portfolio recording.
Never render model text as HTML. The demo uses text nodes and a restrictive
content security policy.

## Reliability evidence

The page exposes durable events/attempts, cancellation of queued work and
retry of eligible failed jobs. It does not contain a failure-injection button
or deliberately kill a worker. Existing [job operations](JOB_LIFECYCLE.md)
and the [controlled interruption](../reports/recovery_demo.json) cover the
actual failure path: the killed active attempt timed out, then an explicit
retry succeeded. Persistence after an already-completed job restart is a
separate check.

If submission times out, inspect Recent jobs before submitting again: the
server may have accepted the request. A failed polling request stops automatic
refresh and displays an error; use Refresh to reconnect. API keys, server-side
attempt limits and job-state rules remain enforced by the service.

## Verification and fallback

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_demo_server.py -q
node tests/demo_ui.test.cjs
```

The Node tests exercise upload/authentication, polling, stale responses, text
rendering and uncertain-submission errors with a mock DOM. They are not visual
browser tests. The preview's HTTP path has also completed a real GPU job; see
[local_demo_acceptance.json](../reports/local_demo_acceptance.json).

The project-created [shapes clip](../assets/portfolio/demo_shapes.mp4) passed a
[real GPU HTTP submission](../reports/demo_shapes_probe.json) on 2026-10-17.
Its synthetic content is a functional input sample, not a quality benchmark.

No browser surface was connected for visual verification in this session.
Browser layout review and an actual screen-recorded walkthrough remain open.
When the GPU host is offline, use saved reports and explain they are historical
evidence; the current UI does not pretend to serve live inference offline.

GPU profiling and a local operations dashboard are available; see
[operations instructions and limits](OPERATIONS.md). The [operational release
and rollback](../reports/release_demo_20261017105931.json) passed with preserved
results. Browser visual review and a recorded walkthrough remain open. Exported
distributed spans and cloud deployment are later extensions.
