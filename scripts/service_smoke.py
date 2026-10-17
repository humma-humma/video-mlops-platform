"""Bounded HTTP acceptance check for the local fake-worker Compose stack."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


def request_json(url: str, data=None, headers=None) -> tuple[int, dict]:
    supplied_headers = dict(headers or {})
    if os.environ.get("VIDEO_API_KEY"):
        supplied_headers["X-API-Key"] = os.environ["VIDEO_API_KEY"]
    request = Request(url, data=data, headers=supplied_headers)
    with urlopen(request, timeout=10) as response:
        return response.status, json.load(response)


def wait_for_job(base_url: str, job_id: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, job = request_json(f"{base_url}/jobs/{job_id}")
        if job["status"] in {"SUCCEEDED", "FAILED"}:
            return job
        time.sleep(1)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout:g}s")


def compose(*args: str) -> str:
    result = subprocess.run(
        ["docker", "compose", *args], cwd=ROOT, check=True,
        capture_output=True, text=True, timeout=60,
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--restart-worker", action="store_true")
    parser.add_argument("--check-failure", action="store_true")
    parser.add_argument("--check-storage", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    base_url = args.base_url.rstrip("/")
    if (args.restart_worker or args.check_failure or args.check_storage) and base_url != "http://localhost:8000":
        parser.error("Compose operations require the default local API URL")
    _, health = request_json(f"{base_url}/health")
    if health["status"] != "ok":
        raise RuntimeError(f"Service is not healthy: {health}")

    boundary = uuid4().hex
    data = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="video"; '
        'filename="smoke.mp4"\r\nContent-Type: video/mp4\r\n\r\n'
    ).encode() + args.video.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    status, submission = request_json(
        f"{base_url}/jobs", data,
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    if status != 202 or submission["status"] != "QUEUED":
        raise RuntimeError(f"Submission was not accepted: {submission}")
    job_id = submission["job_id"]
    job = wait_for_job(base_url, job_id, args.timeout)
    if job["status"] != "SUCCEEDED" or job["result"]["model_version"] != "fake":
        raise RuntimeError(f"Expected a successful fake-worker result: {job}")
    if not job["result"].get("summary"):
        raise RuntimeError("Worker returned an empty summary")
    print(f"PASS submission and asynchronous result: {job_id}")

    if args.check_storage:
        code = (
            "from src.service.db import SessionLocal; "
            "from src.service.models import Job; "
            "from src.service.storage import ArtifactStore; "
            f"db=SessionLocal(); job=db.get(Job, {job_id!r}); "
            "assert job.input_path.startswith('s3://'), job.input_path; "
            "assert job.result_path.startswith('s3://'), job.result_path; "
            "store=ArtifactStore(); assert store.exists(job.input_path); "
            "assert store.get_json(job.result_path)['model_version']=='fake'; "
            "print(job.input_path); print(job.result_path); db.close()"
        )
        compose("exec", "-T", "api", "python", "-c", code)
        print("PASS input and result stored in S3/MinIO")

    if args.restart_worker:
        compose("restart", "worker")
        _, restored = request_json(f"{base_url}/jobs/{job_id}")
        if restored != job:
            raise RuntimeError("Stored result changed after worker restart")
        print("PASS result survives worker restart")

    if args.check_failure:
        # Create a deliberately missing input through the local container only.
        # No failure-injection endpoint is exposed by the API.
        code = (
            "from uuid import uuid4; "
            "from src.service.db import SessionLocal; "
            "from src.service.models import Job; "
            "from src.service.tasks import process_job; "
            "from src.service.config import settings; "
            "job_id=str(uuid4()); "
            "missing=(('s3://'+settings.s3_bucket+'/missing/') if settings.artifact_backend=='s3' else '/artifacts/missing/')+job_id+'.mp4'; "
            "db=SessionLocal(); "
            "db.add(Job(id=job_id,status='QUEUED',input_path=missing)); "
            "db.commit(); db.close(); process_job.delay(job_id); print(job_id)"
        )
        failed_id = compose("exec", "-T", "api", "python", "-c", code).splitlines()[-1]
        failed = wait_for_job(base_url, failed_id, args.timeout)
        if failed["status"] != "FAILED" or failed["error"] != "Input video artifact is missing":
            raise RuntimeError(f"Expected a useful missing-input failure: {failed}")
        print(f"PASS durable failure record: {failed_id}")


if __name__ == "__main__":
    main()
