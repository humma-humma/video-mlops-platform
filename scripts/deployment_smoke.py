"""Exercise the second deployment through the real API and durable job path."""

import argparse
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request(base: str, path: str, api_key: str, payload: dict | None = None):
    headers = {"X-API-Key": api_key} if api_key else {}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(base + path, data=body, headers=headers), timeout=10) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"HTTP {error.code} for {path}: {error.read().decode()}") from error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    api_key = os.environ.get("VIDEO_API_KEY", "")
    deployments = request(base, "/api/v1/deployments", api_key)
    deployment = next(item for item in deployments if item["deployment_id"] == "text-topic-v1")
    submitted = request(base, "/api/v1/deployments/text-topic-v1/jobs", api_key,
                        {"text": "The server runs Python code and a GPU model"})
    job_id = submitted["job_id"]
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        job = request(base, f"/api/v1/jobs/{job_id}", api_key)
        if job["status"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)
    else:
        raise RuntimeError(f"Timed out waiting for {job_id}")
    if job["status"] != "SUCCEEDED":
        raise RuntimeError(f"Job {job_id} ended {job['status']}: {job.get('error')}")
    result = job["result"]
    attempts = request(base, f"/api/v1/jobs/{job_id}/attempts", api_key)
    events = request(base, f"/api/v1/jobs/{job_id}/events", api_key)
    if (job["deployment_id"] != "text-topic-v1" or result["output"]["label"] != "technology"
            or result["model_revision"] != deployment["model_revision"]
            or not result.get("input_sha256") or attempts[-1]["status"] != "SUCCEEDED"
            or not any(event["event"] == "succeeded" for event in events)):
        raise RuntimeError(f"Deployment contract failed for {job_id}")
    print(f"PASS CPU model on shared durable job path: {job_id}")
    print(f"PASS pinned artifact revision: {result['model_revision']}")


if __name__ == "__main__":
    main()
