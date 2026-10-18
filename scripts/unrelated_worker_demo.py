"""Interrupt the idle CPU worker during a real GPU job and export role-aware evidence."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

from scripts.admission_demo import request
from scripts.serving_load import multipart
from src.diagnostics import canonical, diagnose, digest, from_api, validate_bundle


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.gpu.yml"]


def compose(*args):
    run = subprocess.run([*COMPOSE, *args], cwd=ROOT, capture_output=True,
                         text=True, timeout=120)
    if run.returncode:
        raise RuntimeError(f"Compose {args[0]} failed: {run.stderr.strip()}")
    return run.stdout.strip()


def worker_started_at():
    container_id = compose("ps", "-q", "cpu-worker")
    if not container_id:
        raise RuntimeError("CPU worker is not running")
    run = subprocess.run(["docker", "inspect", "--format", "{{.State.StartedAt}}",
                          container_id], capture_output=True, text=True, timeout=15, check=True)
    return run.stdout.strip()


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def get_job(base, job_id):
    code, body = request(f"{base}/api/v1/jobs/{job_id}")
    if code != 200:
        raise RuntimeError(f"GPU job polling returned HTTP {code}")
    return json.loads(body)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path,
                        default=Path("reports/diagnostics/unrelated-worker-live"))
    parser.add_argument("--timeout", type=float, default=240)
    args = parser.parse_args(argv)
    base = args.base_url.rstrip("/")
    if base not in {"http://127.0.0.1:8000", "http://localhost:8000"} or args.timeout <= 0:
        parser.error("Use a local API and a positive timeout")
    code, body = request(base + "/health/ready")
    if code != 200 or json.loads(body).get("status") != "ok":
        raise RuntimeError("Service is not ready")
    compose("up", "-d", "cpu-worker")
    code, metrics = request(base + "/metrics")
    if code != 200:
        raise RuntimeError("Metrics are unavailable")
    match = re.search(r"^video_jobs_outstanding (\d+)$", metrics, re.MULTILINE)
    if not match or int(match[1]) != 0:
        raise RuntimeError("Wait for zero outstanding GPU work")
    code, body = request(base + "/api/v1/jobs?deployment_id=text-topic-v1&limit=100")
    cpu_jobs = json.loads(body) if code == 200 else []
    if code != 200 or len(cpu_jobs) == 100 or any(
            job["status"] in {"PENDING", "QUEUED", "RUNNING"} for job in cpu_jobs):
        raise RuntimeError("Wait for zero outstanding CPU work")
    before = worker_started_at()
    video = args.video.read_bytes()
    body, content_type = multipart(video, None)
    code, response = request(base + "/api/v1/jobs", body, {
        "Content-Type": content_type, "Idempotency-Key": "unrelated-worker-" + uuid4().hex})
    if code != 202:
        raise RuntimeError(f"GPU submission returned HTTP {code}")
    job_id = json.loads(response)["job_id"]
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        job = get_job(base, job_id)
        if job["status"] == "RUNNING":
            break
        if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            raise RuntimeError(f"GPU job ended {job['status']} before CPU interruption")
        time.sleep(0.1)
    else:
        raise TimeoutError("GPU job did not enter RUNNING")
    killed_at = None
    restarted_at = None
    try:
        compose("kill", "-s", "SIGKILL", "cpu-worker")
        killed_at = now()
        compose("up", "-d", "--no-deps", "cpu-worker")
        restarted_at = now()
    finally:
        compose("up", "-d", "--no-deps", "cpu-worker")
    after = worker_started_at()
    if before == after or killed_at is None or restarted_at is None:
        raise RuntimeError("CPU worker restart was not verified")
    while time.monotonic() < deadline:
        job = get_job(base, job_id)
        if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break
        time.sleep(1)
    else:
        raise TimeoutError("GPU job did not settle")
    if job["status"] != "SUCCEEDED" or (job.get("result") or {}).get("model_version") in (None, "fake"):
        raise RuntimeError(f"GPU job did not produce a real result: {job['status']}")
    bundle = from_api(base, job_id, os.environ.get("VIDEO_API_KEY", ""))
    attempts = bundle["observations"]["attempts"]
    if len(attempts) != 1 or attempts[0]["status"] != "SUCCEEDED":
        raise RuntimeError("Expected one successful GPU attempt")
    started = datetime.fromisoformat(attempts[0]["started_at"])
    finished = datetime.fromisoformat(attempts[0]["finished_at"])
    if not started <= datetime.fromisoformat(killed_at) <= finished:
        raise RuntimeError("CPU worker interruption did not overlap the GPU attempt")
    ledger = {
        "schema_version": "unrelated-worker-incident-v1",
        "purpose": "controlled CPU worker interruption during a GPU inference attempt",
        "input_sha256": hashlib.sha256(video).hexdigest(),
        "gpu_job_status": "SUCCEEDED",
        "gpu_attempt_status": "SUCCEEDED",
        "cpu_worker_started_at_before": before,
        "cpu_worker_started_at_after": after,
        "cpu_worker_killed_at": killed_at,
        "cpu_worker_restarted_at": restarted_at,
        "overlap_verified": True,
        "limits": [
            "One local CPU worker interruption does not test a GPU worker failure.",
            "The external event is recorded by this controlled script, not by the job API.",
            "A successful GPU job has no failure cause to diagnose."
        ],
    }
    ledger_raw = write_json(args.output_dir / "ledger.json", ledger)
    bundle["source_kind"] = "live_api_plus_controlled_event"
    bundle["source_sha256"]["report"] = digest(ledger_raw)
    bundle["observations"]["events"].extend([
        {"event": "worker_killed", "generation": None, "timestamp": killed_at,
         "worker_resource": "cpu"},
        {"event": "worker_restarted", "generation": None, "timestamp": restarted_at,
         "worker_resource": "cpu"},
    ])
    bundle["observations"]["events"].sort(key=lambda event: event["timestamp"])
    bundle["missing_evidence"].remove("external_worker_lifecycle_events")
    bundle["bundle_sha256"] = digest(canonical({
        key: value for key, value in bundle.items() if key != "bundle_sha256"}))
    validate_bundle(bundle)
    if diagnose(bundle)["diagnosis"] != "insufficient_evidence":
        raise RuntimeError("Unrelated CPU worker event caused a GPU diagnosis")
    write_json(args.output_dir / "gpu_job_with_cpu_event.json", bundle)
    write_json(args.output_dir / "incident.json", {
        "schema_version": "unrelated-worker-incident-v1",
        "bundle_sha256": bundle["bundle_sha256"],
        "ledger_sha256": digest(ledger_raw),
        "gpu_job_status": "SUCCEEDED",
        "cpu_worker_interruption_overlapped_gpu_attempt": True,
        "diagnosis": "insufficient_evidence",
        "limits": ledger["limits"],
    })
    print("PASS CPU worker interrupted during successful real GPU job; diagnosis abstained")
    print(f"Evidence: {args.output_dir / 'incident.json'}")


if __name__ == "__main__":
    main()
