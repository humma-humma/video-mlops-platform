"""Submit two real GPU jobs and verify model reuse through the HTTP API."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from scripts.service_smoke import request_json, wait_for_job
from src.category_utils import is_canonical_category


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--output", type=Path, default=Path("reports/gpu_service_smoke.json"))
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    base = args.base_url.rstrip("/")
    _, health = request_json(base + "/health")
    if health["status"] != "ok":
        raise RuntimeError(f"Service is not healthy: {health}")
    results = []
    for _ in range(2):
        boundary = uuid4().hex
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="video"; '
            'filename="gpu-smoke.mp4"\r\nContent-Type: video/mp4\r\n\r\n'
        ).encode() + args.video.read_bytes() + b"\r\n"
        if args.transcript:
            body += (
                f'--{boundary}\r\nContent-Disposition: form-data; name="transcript"\r\n\r\n'
            ).encode() + args.transcript.read_bytes() + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        status, submission = request_json(
            base + "/jobs", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        if status != 202:
            raise RuntimeError(f"Job not accepted: {submission}")
        job = wait_for_job(base, submission["job_id"], args.timeout)
        if job["status"] != "SUCCEEDED":
            raise RuntimeError(f"GPU job failed: {job}")
        result = job["result"]
        if result.get("model_version") == "fake" or not result.get("model_revision"):
            raise RuntimeError("Expected a real model with a recorded revision")
        if not result.get("summary") or not is_canonical_category(result.get("category")):
            raise RuntimeError("GPU result violates the summary/category contract")
        results.append(job)
        print(f"PASS real GPU job: {job['job_id']}")
    instances = [job["result"].get("model_instance_id") for job in results]
    if not instances[0] or instances[0] != instances[1]:
        raise RuntimeError("Worker did not reuse the same model instance across jobs")
    if results[1]["result"]["timings"]["model_load"] != 0.0:
        raise RuntimeError("Second job unexpectedly loaded the model again")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"runs": results, "model_reused": True}, indent=2), encoding="utf-8")
    print("PASS model reused across two jobs")


if __name__ == "__main__":
    main()
