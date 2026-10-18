# Unrelated worker interruption control

This controlled case tests whether an interruption on the **CPU** queue is incorrectly attributed to a concurrent **GPU** video job. It uses the real local GPU service. The script checks that both resource backlogs are empty, starts the CPU worker if necessary, submits the known video, kills only `cpu-worker` while the GPU attempt is running, restores it, and requires the GPU job to succeed. It verifies the CPU container start time changed and that the interruption overlapped the GPU attempt.

From the project PowerShell, with the GPU Compose stack running:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.unrelated_worker_demo --video data/inputs/videos/7203774185322188037.mp4
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench evaluate --cases reports/diagnostics/unrelated-worker-live/cases.json --output reports/diagnostics/unrelated-worker-live/evaluation.json
```

The [expected label](../reports/diagnostics/unrelated-worker-live/cases.json) was fixed before collection: `insufficient_evidence` for a GPU failure. The bundle will include a bounded external event with `worker_resource=cpu`, alongside the job's redacted API history. The raw job ID, video and generated text are omitted from the published evidence. The CPU worker is restored in a `finally` block even if the interruption command fails. The script does not change task deadlines or remove volumes.

The historical [GPU recovery report](../reports/recovery_demo.json) has no worker-role field because it predates this schema addition. Its `recovery_report` source is a controlled GPU-worker test and retains the legacy diagnosis. New bundles outside that source must identify `worker_resource=gpu` before a worker-kill event can support `worker_interruption`. A CPU kill plus a GPU timeout therefore remains insufficient to blame the GPU worker. The new role field identifies a resource class, not a particular process or proof that its restart caused a job outcome.

The 2026-10-18 PowerShell run passed. The [incident report](../reports/diagnostics/unrelated-worker-live/incident.json) links a [redacted ledger](../reports/diagnostics/unrelated-worker-live/ledger.json) and [role-aware job bundle](../reports/diagnostics/unrelated-worker-live/gpu_job_with_cpu_event.json). The CPU worker's container start time changed; its kill at 21:13:05 UTC fell between the GPU attempt's 21:13:05 start and 21:13:15 successful finish. The [frozen-case evaluation](../reports/diagnostics/unrelated-worker-live/evaluation.json) matched `insufficient_evidence` (1/1); abstention requires no citations. This shows that the unrelated CPU interruption did not disrupt this one GPU job. It does not measure the behavior of a GPU timeout occurring alongside an unrelated CPU interruption; that combination is covered only by a deterministic unit case.
