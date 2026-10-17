# Local real-GPU worker

The default Compose stack uses fake inference. The GPU override replaces the
same worker service with a CUDA image and the real inference adapter. Keep one
worker process for the two-job model-reuse acceptance check.

## Start

From PowerShell in the repository, with Docker Desktop's Linux engine running:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
& '.\.venv\Scripts\python.exe' -m scripts.gpu_service_smoke --video data/inputs/videos/7203774185322188037.mp4 --transcript data/inputs/audio_transcripts/7203774185322188037.txt
```

The first GPU image build downloads CUDA-enabled Torch and may take substantially
longer than the lightweight API image. The model cache is mounted read-only from
`$env:USERPROFILE/.cache/huggingface`; set `VIDEO_HF_CACHE` to its directory if it
is elsewhere. The worker runs offline and requires the already-downloaded
`HuggingFaceTB/SmolVLM2-500M-Video-Instruct` snapshot
`7b375e1b73b11138ff12fe22c8f2822d8fe03467`. A missing checkpoint produces a failed
job rather than an implicit model download. The 500M model is a hardware/service
smoke target, not the 2.2B research baseline.

GPU access uses a single NVIDIA device reservation, following the
[Docker Compose GPU configuration](https://docs.docker.com/compose/how-tos/gpu-support/).
The dedicated worker runtime pins Torch 2.8.0, torchvision 0.23.0, CUDA 12.6, and
Transformers 4.56.1 to match the existing economical GPU smoke's model stack.
TorchCodec 0.7.0 provides bounded frame decoding. The build verifies its FFmpeg
import, the worker requires it before allocating model weights, and frame
sampling is explicitly enabled. Rebuild the worker image to receive these
changes; restarting an existing container does not update its runtime.
The Torch wheel pair follows the
[official version matrix](https://pytorch.org/get-started/previous-versions/).
This is a separate minimal serving environment; it does not claim equivalence
with the research `uv.lock` environment, which targets newer Torch versions.

## Behavior

- The API accepts an optional UTF-8 `transcript` form field, stores it beside
  the video, and limits its length.
- The GPU worker downloads the video to a per-job temporary directory and reads
  an optional transcript artifact. Scratch files are removed when the job exits.
- Without a transcript, inference uses visuals only. Automatic Whisper
  transcription is not connected to this service adapter yet.
- Model and processor loading use the pinned revision. Loading occurs lazily
  inside a Celery child, and the model stays cached in that process across jobs.
- Results include a canonical category, model revision, instance ID, transcript
  source, and stage timings. First-use model loading is timed separately.
- Missing/invalid output and runtime failures become durable `FAILED` jobs.
- The two-job smoke rejects fake outputs and checks model-instance reuse and
  zero repeated model-load time. Its JSON evidence is written to
  `reports/gpu_service_smoke.json` only after both jobs pass.

## Return to fake mode

```powershell
docker compose up --build -d
```

The override replaces the existing worker, rather than adding a second worker
that might consume jobs from the same queue in an unexpected mode.
