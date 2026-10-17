# MinIO/S3 implementation — 2026-10-09

## Implemented

- Configurable filesystem and S3-compatible artifact storage.
- S3 object URIs for inputs and results, JSON retrieval, object existence checks,
  and download-to-file support.
- Explicit bucket bootstrap with bounded SDK timeouts/retries and startup retry.
- Separate handling of missing objects and storage/permission failures.
- Stream closure after reads, bucket URI validation, and relative-key checks.
- Compatibility reads for existing filesystem-backed job records.
- API dependency errors, worker result-upload failure recording, and artifact
  readiness in the health response.
- Persistent MinIO volume and Compose startup dependency on bucket bootstrap.
- Smoke assertions for actual S3 input/result references and object retrieval.

## Verification

- Service and storage contract tests: **30 passed** using an injected S3 client
  and SQLite. A temporary workspace fixture plugin avoids this agent session's
  Windows temporary-directory permissions issue; test bodies are unchanged.
- Existing inference suite: **20 passed**.
- Compose configuration, Python compilation, and whitespace checks: **passed**.
- Real MinIO/S3 acceptance: **passed** after rebuild. The user ran the full
  external Docker smoke command and supplied four passing checks: asynchronous
  result, S3/MinIO input/result storage, persistence after worker restart, and a
  durable missing-input failure. This exercises the container's Boto3 client,
  bucket bootstrap, uploads, reads, and missing-object behavior against MinIO.
- Successful job: `7be30fe4-dbff-4da6-9d78-ab4a07e4945e`.
- Deliberately failing job: `060d1889-8d2f-4177-abec-43b6af803bfd`.
- The agent independently confirmed both final job states and the expected
  missing-input error over HTTP. `/health` reports database, queue, and storage
  `ok`. Docker restart/control evidence comes from the user's smoke output,
  since the agent session cannot access Docker's control pipe.

## Repeat external verification

From PowerShell in the repository:

```powershell
docker compose up --build -d
& '.\.venv\Scripts\python.exe' -m scripts.service_smoke --video data/inputs/videos/7203774185322188037.mp4 --restart-worker --check-failure --check-storage
```

Expected checks: asynchronous result, input/result stored in S3/MinIO, stored
result after worker restart, and a durable failure for a missing S3 input.

The GPU adapter is now implemented and verified natively and through Docker.
The remaining production contracts of Artifact C are unfinished. See
`gpu_worker_status.md`.
