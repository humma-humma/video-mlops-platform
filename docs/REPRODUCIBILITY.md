# Reproducibility boundary

The checked-in Python 3.12 snapshots [for the service](../requirements-service.lock.txt) and [for CPU tests](../requirements-service-test.lock.txt) record the distributions in the working Windows `.venv` on 2026-10-20. `Dockerfile` and the GPU/benchmark Dockerfiles install the service snapshot; GitHub Actions and `scripts/verify_local.ps1` install the test snapshot. The Python base image is pinned to a reviewed manifest digest. The small CPU model is committed with a stable SHA-256; GPU Torch, TorchVision, Transformers, Accelerate and TorchCodec use exact direct versions.

From a fresh clone with Python 3.12, Node.js and Docker:

```powershell
py -3.12 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-service-test.lock.txt
& '.\.venv\Scripts\python.exe' -m pip check
& '.\.venv\Scripts\python.exe' -m pytest -q
node tests/demo_ui.test.cjs
node tests/operations_ui.test.cjs
$env:VIDEO_S3_ENDPOINT_URL = 'http://minio:9090'
docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build --wait
```

The fresh-clone Compose path uses S3Mock. The historical MinIO image is not reliably pullable anonymously and its existing named volume must not be silently replaced. The CI workflow exercises the fresh-clone CPU/fake-video service path; real GPU and MinIO acceptance is recorded separately on the local host. Do not interpret the fake-worker result as a real VLM run.

To refresh the Python snapshots, first install/review changes in a clean Python 3.12 environment, run the full CPU tests and Compose smoke, then run:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.freeze_service_requirements
git diff -- requirements-service.lock.txt requirements-service-test.lock.txt
```

The snapshot generator follows installed package metadata from the nine service roots; the test file captures all distributions in that test environment. Review every version change and verify Linux CI before merging. It is a version snapshot, not a cross-platform hash lock: wheels, Linux-only optional packages, OS libraries and mutable Compose dependency tags can still vary. The GPU worker's full transitive environment has not been captured from its container. `uv.lock` belongs to the older research environment, not this serving stack. The project claims a tested, version-pinned CPU path and documented GPU revisions, **not** bit-for-bit reproduction of every image and CUDA runtime.
