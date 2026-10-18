# Controlled damaged-video incident

This check uses the real local GPU service, not a simulated adapter. It generates a 3-second synthetic H.264 MP4 and a damaged copy that retains its container metadata but has no frame payload. Local `ffprobe` accepts both files; a full local `ffmpeg` decode succeeds only for the intact file. The service's metadata-only admission check therefore accepts the damaged upload, while its GPU worker later fails during inference. It also runs a known video through the GPU worker as a successful service control.

From the project PowerShell, with the GPU Compose stack running and the backlog empty:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.decoder_incident_demo `
  --control-video data/inputs/videos/7203774185322188037.mp4 `
  --control-transcript data/inputs/audio_transcripts/7203774185322188037.txt
```

Use a control video that has already succeeded on this deployment if the example file is unavailable. The script needs host FFmpeg/ffprobe and a real GPU worker. It stores generated MP4s only under ignored `data/outputs/decoder-incident-work/`. It does not stop containers or alter the worker. Allow several minutes for model loading and generation.

The [fixture ledger](../reports/diagnostics/decoder-live/fixture_ledger.json) records the MP4 construction, input hashes and local probe/decode controls. The [incident report](../reports/diagnostics/decoder-live/incident.json) links the [successful control job](../reports/diagnostics/decoder-live/healthy_job.json) and [failed damaged job](../reports/diagnostics/decoder-live/damaged_job.json) by bundle hash. On 2026-10-18, the known video succeeded, while the damaged upload yielded one `inference` attempt failure. The workbench returned `insufficient_evidence` for that job. Pairwise timing comparison was also refused because the inputs differ and a failed job has no successful-result timing lineage.

The initial intact synthetic test-pattern clip decoded locally but failed the GPU job; its [redacted record](../reports/diagnostics/decoder-live/test_pattern_control.json) is a second example of a generic `inference` failure. The [two-case evaluation](../reports/diagnostics/decoder-live/evaluation.json) checks that the workbench abstains on both. These cases were selected after observation; 2/2 abstentions are a safety check, not a diagnosis-accuracy estimate.

The injected defect is known from the fixture construction and FFmpeg controls. The exported job evidence does **not** show the worker's exact TorchCodec exception or a decoder-specific stage; the service reports only `inference`. Thus the result demonstrates an observability and admission gap, not independent decoder-root-cause identification. The fixture's metadata and full-decode checks can be reproduced without submitting jobs; the live job evidence depends on the local GPU stack. No raw video, generated text, transcript, job ID, free-form error or worker log is included in the published bundles.

## Repair and acceptance

The repaired `VideoAdapter` now uses FFmpeg to decode **one frame** from the downloaded video before loading the GPU model. The subprocess has a 15-second timeout, allows only local file/pipe protocols and discards decoder output. A nonzero decoder exit becomes the durable attempt code `decode_failed`; timeout and unavailable-executable conditions have separate codes. The worker's structured event uses `decode_preflight` as its stage. The workbench reports `reported_decode_failure` only for a failed attempt bearing `decode_failed`, with citations to status and code. Generic `inference` failures still cause abstention.

This is a bounded guard, not exhaustive media validation. Damage in later frames or a TorchCodec-specific failure after FFmpeg succeeds can still surface as a generic inference failure. The code says only that FFmpeg could not produce the first frame; it does not establish whether the file is corrupt, the codec is unsupported or the decoder itself is faulty. API admission remains metadata-only, so an undecodable upload can still create a job; the worker now fails it before model loading. Full decoding at API admission would spend more CPU on every request and would delay asynchronous submission.

After rebuilding the GPU worker, repeat the experiment without overwriting the historical evidence:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build worker
& '.\.venv\Scripts\python.exe' -m scripts.decoder_incident_demo `
  --control-video data/inputs/videos/7203774185322188037.mp4 `
  --control-transcript data/inputs/audio_transcripts/7203774185322188037.txt `
  --expect-decode-preflight `
  --output-dir reports/diagnostics/decoder-live-v2
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench evaluate `
  --cases reports/diagnostics/decoder-live-v2/cases.json `
  --output reports/diagnostics/decoder-live-v2/evaluation.json
```

The 2026-10-18 rerun passed against the rebuilt GPU worker. The [v2 incident report](../reports/diagnostics/decoder-live-v2/incident.json) links the [successful known-video job](../reports/diagnostics/decoder-live-v2/healthy_job.json), [failed damaged job](../reports/diagnostics/decoder-live-v2/damaged_job.json) and [fixture ledger](../reports/diagnostics/decoder-live-v2/fixture_ledger.json). The ledger records the same healthy and damaged SHA-256 inputs as the historical run. The damaged attempt now records `decode_failed` instead of `inference`; the workbench returns `reported_decode_failure` instead of `insufficient_evidence`. The [pre-specified v2 case](../reports/diagnostics/decoder-live-v2/cases.json) matched with valid citations [1/1](../reports/diagnostics/decoder-live-v2/evaluation.json). This is one controlled development case, not an estimate of independent incident accuracy. The pairwise latency comparison still abstains because the inputs differ and the damaged job failed. The API, dispatcher, CPU worker and named volumes did not need replacement.
