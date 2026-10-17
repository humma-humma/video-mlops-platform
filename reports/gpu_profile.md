# Local GPU profile — 2026-10-10

Completed direct inference of the existing development sample
`7203774185322188037`, without submitting a video or creating an API job.
All 16 existing job IDs were unchanged. No cloud resources were used.

| Measurement | Observed value |
|---|---:|
| Cached model load | 2.50 s |
| Two-pass warmup | 21.69 s |
| Profiled summary pass | 20.91 s |
| Profiled category pass | 6.21 s |
| Peak process CUDA allocation | 1,541.63 MiB |
| Peak process CUDA reservation | 1,622 MiB |
| Device usage before model load | 3,314 MiB, 0% utilization |

Environment: RTX 2080, native Windows Python 3.10.13, Torch 2.8.0+cu126,
Transformers 4.56.1. Pinned 500M SmolVLM2 revision
`7b375e1b73b11138ff12fe22c8f2822d8fe03467`, four sampled frames,
KV cache enabled, dtype selection `auto`. Summary/category calls include video
preprocessing and generation; they are not pure kernel timings. The native
decoder fell back to torchvision. Existing GPU activity was observed during
preflight, but the recorded baseline sample was at 0% utilization; neither
observation establishes exclusive use of the GPU.

The [machine-readable report](gpu_profile.json) records input hashes, model/config,
environment, device-wide samples, before/after job IDs and artifact hashes. Raw
trace and operator table are local in `data/outputs/gpu-profile/`. The compressed
trace is approximately 63 MB; its decompressed SHA-256 was checked against the
original 729 MB trace. Both remain ignored local artifacts.

The first run enabled memory-event tracing and incurred substantial export and
aggregation overhead. The runner now disables memory-event tracing for later
runs while retaining CUDA allocator peak measurements. The recorded evidence
explicitly retains the original setting. No rerun is represented here.

The operator table contains matrix multiplication and copy work, but its CUDA
percentages include annotations and can exceed 100%; do not use them as GPU
utilization, additive stage percentages or a bottleneck ranking. The count is
CUDA **device events**, not a validated kernel count. Use the trace for diagnosis.

This is one input with one warmup and one measured run, with profiler overhead
and possible device sharing. It proves active profiling works; it does not
establish a latency SLO, sustained capacity, decoder memory bounds, a model
optimization win, or acceptance of the rebuilt Docker/TorchCodec worker.
