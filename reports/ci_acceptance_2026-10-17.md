# Remote delivery check — 2026-10-17

[GitHub Actions run 39025177821](https://github.com/humma-humma/video-mlops-platform/actions/runs/39025177821)
completed successfully on `main` after commit `9a12725`. The owner supplied
the run result from GitHub CLI; the agent's session could not directly access
GitHub. The `Checks` workflow runs the full Python CPU suite, six Node
UI/dashboard behavior checks, `git diff --check`, Compose configuration and a
fake-worker service smoke including worker restart, durable failure and S3 API
input/result retrieval.

The Compose job substitutes `adobe/s3mock:5.2.3` through
`docker-compose.ci.yml` because fresh runners could not anonymously pull the
historical MinIO images. S3Mock is a test double; this run does not establish
MinIO behavior or real CUDA inference. Those claims rely on the separate
[rebuilt GPU smoke](gpu_service_smoke_current.json), [MinIO integration
evidence](minio_integration_status.md), [active recovery](recovery_demo.json)
and [release/rollback report](release_demo_20261017105931.json) from the local
host. The operational release preceded these commits and is not a CI-linked
immutable artifact.

Earlier failed runs are retained in GitHub Actions: `39024674204` exposed
missing manifest fixtures and a Docker Hub image pull; `39024893980` passed
the CPU job but found that the Quay image also rejected anonymous pulls.
The fixes narrowed the CI storage dependency without changing the local
MinIO volume or production claims.
