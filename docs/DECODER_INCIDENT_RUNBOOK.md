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
