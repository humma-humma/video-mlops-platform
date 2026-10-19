# CPU model artifact incident (pending live acceptance)

The [protocol](../reports/diagnostics/model-artifact-live/protocol.json) was committed as `6297a1d` before the repair. It registers a different failure family from the prior MinIO and result-object incidents: the CPU worker cannot read its own packaged model file, while the submitted input remains present. Before the repair, the generic `FileNotFoundError` classifier would have recorded `missing_input`. That prediction is from source inspection, **not** a historical live observation.

The repair raises a typed `ModelArtifactUnavailable` only when the text model's packaged file cannot be read. The worker records `model_artifact_unavailable`; the workbench reports the recorded code with citations. It does not infer why the file is missing. A genuine missing submitted input still maps to `missing_input`, and generic inference failures still abstain.

After rebuilding the local CPU worker with this source, run from the project PowerShell:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build cpu-worker
& '.\.venv\Scripts\python.exe' -m scripts.model_artifact_incident
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench evaluate `
  --cases reports/diagnostics/model-artifact-live/cases.json `
  --output reports/diagnostics/model-artifact-live/evaluation.json
```

The script requires a healthy local API and zero outstanding CPU jobs. It hashes the CPU worker's model artifact, hides only that container file, restarts the CPU worker to clear its model cache, and submits one synthetic text job. In `finally`, it restores the exact file and restarts the worker. It then submits a control job and checks success. It refuses to overwrite evidence from a previous run. If restoration fails, inspect `run_state.json` and restore the file before using the CPU worker. The intervention changes the local CPU-worker container's writable layer temporarily; it does not modify the image, host source, GPU worker or an existing job's artifact.

The [pre-registered case manifest](../reports/diagnostics/model-artifact-live/cases.json) marks this a **development** acceptance case because the new rule was designed for this mechanism. A passing 1/1 would validate the repaired deployed path, not independent diagnostic accuracy. The missing-input confounder is checked in code; a separate live confounder would be needed for stronger evidence.
