"""Interrupt a real running GPU job and record its observed recovery path."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from scripts.admission_demo import request
from scripts.serving_load import multipart


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.gpu.yml"]


def compose(*args, env=None):
    run = subprocess.run([*COMPOSE, *args], cwd=ROOT, env=env, capture_output=True,
                         text=True, timeout=240, check=True)
    return run.stdout.strip()


def get_json(base, path, data=None, headers=None):
    code, body = request(base + path, data, headers)
    return code, json.loads(body)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("reports/recovery_demo.json"))
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    base = args.base_url.rstrip("/")
    if base not in {"http://127.0.0.1:8000", "http://localhost:8000"}:
        parser.error("This destructive worker test requires the local API")
    code, ready = get_json(base, "/health/ready")
    if code != 200 or ready["status"] != "ok":
        raise RuntimeError("Service is not ready")
    code, metrics = request(base + "/metrics")
    if code != 200 or "video_jobs_outstanding 0\n" not in metrics:
        raise RuntimeError("Current API and an empty backlog are required")
    original = json.loads(compose("exec", "-T", "dispatcher", "python", "-c",
        "import json; from src.service.config import settings; "
        "print(json.dumps([settings.task_soft_time_limit, settings.task_time_limit]))").splitlines()[-1])
    if original[0] >= original[1]:
        raise RuntimeError("Invalid deployed task deadlines")
    demo_env = os.environ.copy()
    demo_env.update(VIDEO_TASK_SOFT_TIME_LIMIT="180", VIDEO_TASK_TIME_LIMIT="240")
    restore_env = os.environ.copy()
    restore_env.update(VIDEO_TASK_SOFT_TIME_LIMIT=str(original[0]), VIDEO_TASK_TIME_LIMIT=str(original[1]))
    video = args.video.read_bytes()
    body, content_type = multipart(video, None)
    timeline = []
    job_id = None

    def note(event, **details):
        entry = {"at": datetime.now(timezone.utc).isoformat(), "event": event, **details}
        timeline.append(entry)
        print(f"{entry['at']} {event} {details}", flush=True)

    try:
        compose("up", "-d", "--no-deps", "--force-recreate", "dispatcher", "worker", env=demo_env)
        note("demo_deadlines_active", soft_seconds=180, hard_seconds=240)
        code, submission = get_json(base, "/api/v1/jobs", body,
            {"Content-Type": content_type, "Idempotency-Key": "recovery-demo-" + os.urandom(16).hex()})
        if code != 202:
            raise RuntimeError(f"Submission failed: {code} {submission}")
        job_id = submission["job_id"]
        note("submitted", job_id=job_id)
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            _, job = get_json(base, "/api/v1/jobs/" + job_id)
            if job["status"] == "RUNNING":
                note("running")
                break
            if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                raise RuntimeError(f"Job reached {job['status']} before interruption")
            time.sleep(.2)
        else:
            raise TimeoutError("Job never entered RUNNING")
        compose("kill", "-s", "SIGKILL", "worker", env=demo_env)
        note("worker_killed", signal="SIGKILL", worker_resource="gpu")
        compose("up", "-d", "--no-deps", "worker", env=demo_env)
        note("worker_restarted", worker_resource="gpu")
        seen = None
        while time.monotonic() < deadline:
            _, job = get_json(base, "/api/v1/jobs/" + job_id)
            if job["status"] != seen:
                note("job_status", status=job["status"])
                seen = job["status"]
            if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                break
            time.sleep(2)
        else:
            raise TimeoutError(f"Interrupted job {job_id} did not settle")
        if job["status"] == "FAILED":
            code, retried = get_json(base, "/api/v1/jobs/" + job_id + "/retry", b"")
            if code != 202:
                raise RuntimeError(f"Explicit retry unavailable: {code} {retried}")
            note("explicit_retry_requested")
            while time.monotonic() < deadline:
                _, job = get_json(base, "/api/v1/jobs/" + job_id)
                if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    break
                time.sleep(2)
            else:
                raise TimeoutError("Retry did not settle")
        if job["status"] != "SUCCEEDED" or (job.get("result") or {}).get("model_version") in {None, "fake"}:
            raise RuntimeError(f"Recovery did not produce a real GPU result: {job['status']}")
        note("result_persisted", model_revision=job["result"].get("model_revision"))
        _, attempts = get_json(base, "/api/v1/jobs/" + job_id + "/attempts")
        _, events = get_json(base, "/api/v1/jobs/" + job_id + "/events")
        report = {"schema_version": "1", "purpose": "controlled local active-worker interruption",
                  "input_sha256": hashlib.sha256(video).hexdigest(), "job_id": job_id,
                  "original_soft_hard_seconds": original, "demo_soft_hard_seconds": [180, 240],
                  "timeline": timeline, "attempts": attempts, "events": events,
                  "final_status": job["status"], "result_model_revision": job["result"].get("model_revision"),
                  "limits": ["Hard interruption can remain RUNNING until deadline plus reconciliation allowance.",
                             "The explicit retry is part of this observed recovery; execution is not exactly once."]}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    finally:
        compose("up", "-d", "--no-deps", "--force-recreate", "dispatcher", "worker", env=restore_env)
        note("original_deadlines_restored", soft_seconds=original[0], hard_seconds=original[1])
        if "report" in locals():
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS active-worker interruption and persisted recovery: {job_id}")
    print(f"Evidence: {args.output}")


if __name__ == "__main__":
    main()
