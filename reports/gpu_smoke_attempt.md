# GPU Smoke Attempt

## Purpose

Verify the real CUDA/model execution path and compare isolated two-pass inference with strict combined summary/category generation. This is a hardware and integration smoke test, not a production quality baseline.

## Environment

- Date: 2026-08-29
- GPU: NVIDIA GeForce RTX 2080, 8 GB
- Driver: 591.86
- Python environment: `mardm`
- PyTorch: 2.8.0+cu126
- Transformers: 4.56.1
- CUDA available: yes
- Economical smoke model: `HuggingFaceTB/SmolVLM2-500M-Video-Instruct`
- Requested frames: 4
- Video: `7302484543691328810`

The production target remains `HuggingFaceTB/SmolVLM2-2.2B-Instruct`. The 500M model was selected only to validate the implementation on available 8 GB hardware without a larger download or paid GPU.

## Result

**Blocked before inference.**

The existing Hugging Face cache contained tokenizer/configuration files but no model checkpoint. Model loading therefore failed with:

```text
AttributeError: 'NoneType' object has no attribute 'endswith'
```

A bounded download of the 500M checkpoint was approved and attempted. It timed out after 604 seconds without transferring checkpoint bytes. The cache contains zero-byte resumable `.incomplete` files, so no latency, output-quality, or memory result is reported.

This is an external model-asset/download blocker, not a passing GPU benchmark.

## Rerun

After the checkpoint becomes available, run:

```powershell
$env:HF_HUB_OFFLINE='1'
& 'C:\Users\mopu01\AppData\Local\anaconda3\envs\mardm\python.exe' `
  -m scripts.gpu_smoke `
  --video data/inputs/videos/7302484543691328810.mp4 `
  --transcript data/inputs/audio_transcripts/7302484543691328810.txt `
  --max-frames 4 `
  --output reports/gpu_smoke_500m.json
```

Acceptance requires both strategies to produce a report, peak GPU memory to remain within the device limit, and combined output to pass the strict JSON/taxonomy parser. A separate 2.2B baseline is still required on suitable hardware.
