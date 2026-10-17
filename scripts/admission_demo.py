"""Bounded concurrent burst demonstrating the GPU backlog admission limit."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from scripts.serving_load import multipart


def request(url, data=None, headers=None):
    headers = dict(headers or {})
    if os.environ.get("VIDEO_API_KEY"):
        headers["X-API-Key"] = os.environ["VIDEO_API_KEY"]
    try:
        with urlopen(Request(url, data=data, headers=headers), timeout=30) as response:
            return response.status, response.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()


def metric(body, name):
    match = re.search(rf"^{re.escape(name)} (\d+)$", body, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Missing {name} metric; deploy the current API image")
    return int(match[1])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--output", type=Path, default=Path("reports/admission_demo.json"))
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    base = args.base_url.rstrip("/")
    if base not in {"http://127.0.0.1:8000", "http://localhost:8000"}:
        parser.error("This controlled demo requires the local API")
    code, ready = request(base + "/health/ready")
    if code != 200 or json.loads(ready)["status"] != "ok":
        raise RuntimeError("Service is not ready")
    code, metrics = request(base + "/metrics")
    if code != 200:
        raise RuntimeError("Metrics endpoint is unavailable")
    capacity = metric(metrics, "video_job_capacity")
    if not 1 <= capacity <= 3:
        raise RuntimeError("Set VIDEO_MAX_OUTSTANDING_JOBS to 1, 2 or 3 for this capped demo")
    if metric(metrics, "video_jobs_outstanding") != 0:
        raise RuntimeError("Wait for existing queued/running jobs before this demo")
    video = args.video.read_bytes()
    body, content_type = multipart(video, None)
    started = datetime.now(timezone.utc).isoformat()

    def submit(index):
        key = "admission-demo-" + uuid4().hex
        code, payload = request(base + "/api/v1/jobs", body,
                                {"Content-Type": content_type, "Idempotency-Key": key})
        return {"index": index, "http_status": code, "response": json.loads(payload)}

    with ThreadPoolExecutor(max_workers=capacity + 1) as pool:
        submissions = list(pool.map(submit, range(capacity + 1)))
    accepted = [row for row in submissions if row["http_status"] == 202]
    rejected = [row for row in submissions if row["http_status"] == 429]
    if len(accepted) != capacity or len(rejected) != 1:
        raise RuntimeError(f"Expected {capacity} accepts and one capacity rejection; got {submissions}")
    outcomes = []
    deadline = time.monotonic() + args.timeout
    def wait_for_result(row):
        job_id = row["response"]["job_id"]
        while time.monotonic() < deadline:
            code, payload = request(base + "/api/v1/jobs/" + job_id)
            job = json.loads(payload)
            if code == 200 and job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                return {"job_id": job_id, "status": job["status"],
                        "model_version": (job.get("result") or {}).get("model_version")}
            time.sleep(1)
        raise TimeoutError(f"Accepted job {job_id} remains active; inspect it before retrying")
    for row in accepted:
        outcomes.append(wait_for_result(row))
    if any(row["status"] != "SUCCEEDED" or row["model_version"] in {None, "fake"} for row in outcomes):
        raise RuntimeError(f"An accepted job did not succeed: {outcomes}")
    recovery = submit("after_drain")
    if recovery["http_status"] != 202:
        raise RuntimeError(f"Capacity did not recover after draining: {recovery}")
    recovered = wait_for_result(recovery)
    if recovered["status"] != "SUCCEEDED" or recovered["model_version"] in {None, "fake"}:
        raise RuntimeError(f"After-drain GPU job failed: {recovered}")
    report = {"schema_version": "1", "purpose": "local GPU admission demonstration",
              "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
              "input_sha256": hashlib.sha256(video).hexdigest(), "capacity": capacity,
              "submissions": submissions, "terminal_outcomes": outcomes,
              "after_drain": recovery, "after_drain_outcome": recovered, "passed": True,
              "limits": ["One small local burst does not establish sustained capacity or tail latency.",
                         "GPU utilization and competing host workloads are not sampled by this script."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS {capacity} accepted, one 429 rejected, acceptance resumed after drain")
    print(f"After-drain job: {recovery['response']['job_id']}")
    print(f"Evidence: {args.output}")


if __name__ == "__main__":
    main()
