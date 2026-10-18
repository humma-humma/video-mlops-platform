# Unrelated worker interruption control

This controlled case tests whether an interruption on the **CPU** queue is incorrectly attributed to a concurrent **GPU** video job. It uses the real local GPU service. The script checks that both resource backlogs are empty, starts the CPU worker if necessary, submits the known video, kills only `cpu-worker` while the GPU attempt is running, restores it, and requires the GPU job to succeed. It verifies the CPU container start time changed and that the interruption overlapped the GPU attempt.

From the project PowerShell, with the GPU Compose stack running:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.unrelated_worker_demo --video data/inputs/videos/7203774185322188037.mp4
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench evaluate --cases reports/diagnostics/unrelated-worker-live/cases.json --output reports/diagnostics/unrelated-worker-live/evaluation.json
```

The [expected label](../reports/diagnostics/unrelated-worker-live/cases.json) was fixed before collection: `insufficient_evidence` for a GPU failure. The bundle will include a bounded external event with `worker_resource=cpu`, alongside the job's redacted API history. The raw job ID, video and generated text are omitted from the published evidence. The CPU worker is restored in a `finally` block even if the interruption command fails. The script does not change task deadlines or remove volumes.

The historical [GPU recovery report](../reports/recovery_demo.json) has no worker-role field because it predates this schema addition. Its `recovery_report` source is a controlled GPU-worker test and retains the legacy diagnosis. New bundles outside that source must identify `worker_resource=gpu` before a worker-kill event can support `worker_interruption`. A CPU kill plus a GPU timeout therefore remains insufficient to blame the GPU worker. The new role field identifies a resource class, not a particular process or proof that its restart caused a job outcome.

This case is pending execution from a PowerShell session with Docker engine access. Do not count it as live evidence until the script completes, the exported bundle validates, and the frozen-case evaluation is checked.
