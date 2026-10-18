"""Capture a real local MinIO outage, failed CPU job, and recovered retry."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.diagnostic_workbench import write_json
from src.diagnostics import canonical, digest, from_api, validate_bundle


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.gpu.yml"]
SERVICES = ("minio", "cpu-worker", "dispatcher")
SAMPLE = "The server runs Python code and a GPU model"


def compose(*args: str) -> str:
    run = subprocess.run([*COMPOSE, *args], cwd=ROOT, text=True,
                         capture_output=True, check=True, timeout=120)
    return run.stdout.strip()


def running_services() -> set[str]:
    return set(compose("ps", "--services", "--status", "running").splitlines())


def start_existing_container(service: str) -> None:
    """Start only the selected container; Compose start also starts its dependencies."""
    if service != "cpu-worker":
        raise ValueError("Only the CPU worker may bypass Compose dependencies")
    ids = compose("ps", "-a", "-q", service).splitlines()
    if len(ids) != 1 or not re.fullmatch(r"[0-9a-f]{12,64}", ids[0]):
        raise RuntimeError("Expected exactly one existing CPU-worker container")
    subprocess.run(["docker", "start", ids[0]], cwd=ROOT, text=True,
                   capture_output=True, check=True, timeout=120)


def request(base: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if key := os.environ.get("VIDEO_API_KEY"):
        headers["X-API-Key"] = key
    try:
        with urlopen(Request(base + path, data=body, headers=headers), timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def wait_job(base: str, job_id: str, target: str, deadline: float) -> dict:
    while time.monotonic() < deadline:
        code, job = request(base, "/api/v1/jobs/" + job_id)
        if code != 200:
            raise RuntimeError(f"Job read returned HTTP {code}")
        if job["status"] == target:
            return job
        if job["status"] in {"FAILED", "SUCCEEDED", "CANCELLED"}:
            raise RuntimeError(f"Job reached {job['status']} instead of {target}")
        time.sleep(1)
    raise TimeoutError(f"Job did not reach {target} before the deadline")


def wait_ready(base: str, deadline: float) -> None:
    while time.monotonic() < deadline:
        try:
            code, health = request(base, "/health/ready")
            if code == 200 and health.get("status") == "ok":
                return
        except (OSError, ValueError):
            pass
        time.sleep(2)
    raise TimeoutError("Service did not become ready after MinIO restart")


def active_jobs(base: str) -> list[dict]:
    active = []
    for offset in range(0, 1000, 100):
        code, page = request(base, f"/api/v1/jobs?limit=100&offset={offset}")
        if code != 200 or not isinstance(page, list):
            raise RuntimeError("Could not check current job backlog")
        active.extend(job for job in page if job["status"] in {"PENDING", "QUEUED", "RUNNING"})
        if len(page) < 100:
            return active
    raise RuntimeError("Job inventory exceeds the bounded preflight")


def matching_failure_log(raw: str, job_id: str) -> tuple[str, str]:
    matches = []
    for line in raw.splitlines():
        brace = line.find("{")
        if brace < 0:
            continue
        try:
            item = json.loads(line[brace:])
        except json.JSONDecodeError:
            continue
        if item.get("event") == "worker_failure" and item.get("job_id") == job_id:
            matches.append((item.get("stage"), item.get("error_code"), line[brace:]))
    if len(matches) != 1 or matches[0][:2] != ("artifact_check", "dependency"):
        raise RuntimeError("Expected exactly one structured artifact-check dependency failure")
    return matches[0][0], digest(matches[0][2].encode())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/diagnostics/minio-live"))
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    base = args.base_url.rstrip("/")
    if base not in {"http://127.0.0.1:8000", "http://localhost:8000"} or args.timeout < 60:
        parser.error("Use the local API and a timeout of at least 60 seconds")
    if not set(SERVICES).issubset(running_services()):
        raise RuntimeError("MinIO, CPU worker and dispatcher must already be running")
    wait_ready(base, time.monotonic() + 15)
    if active_jobs(base):
        raise RuntimeError("Existing jobs are active; wait for the backlog to drain")

    timeline = []
    job_id = None
    deadline = time.monotonic() + args.timeout

    def note(event: str):
        timeline.append({"event": event, "timestamp": datetime.now(timezone.utc).isoformat()})
        print(event, flush=True)

    try:
        compose("stop", "dispatcher", "cpu-worker")
        note("dispatch_and_cpu_worker_stopped")
        code, submission = request(base, "/api/v1/deployments/text-topic-v1/jobs", {"text": SAMPLE})
        if code != 202:
            raise RuntimeError(f"CPU job submission returned HTTP {code}")
        job_id = submission["job_id"]
        note("test_job_queued")
        log_start = datetime.now(timezone.utc).isoformat()
        compose("stop", "minio")
        note("minio_stopped")
        start_existing_container("cpu-worker")
        if "minio" in running_services():
            raise RuntimeError("MinIO restarted before the worker could observe the outage")
        note("cpu_worker_started_during_outage")
        failed = wait_job(base, job_id, "FAILED", deadline)
        note("job_failed_during_outage")
        _, attempts = request(base, f"/api/v1/jobs/{job_id}/attempts")
        if len(attempts) != 1 or attempts[0].get("error_code") != "dependency":
            raise RuntimeError("First attempt was not a dependency failure")
        logs = compose("logs", "--no-color", "--since", log_start, "cpu-worker")
        stage, log_hash = matching_failure_log(logs, job_id)
        bundle = from_api(base, job_id, os.environ.get("VIDEO_API_KEY", ""))
        bundle["observations"]["failure_stage"] = stage
        bundle["source_sha256"]["structured_log"] = log_hash
        bundle["bundle_sha256"] = digest(canonical({k: v for k, v in bundle.items()
                                                    if k != "bundle_sha256"}))
        validate_bundle(bundle)
        write_json(args.output_dir / "failed_job.json", bundle)
        note("redacted_failure_bundle_saved")

        compose("start", "minio")
        wait_ready(base, deadline)
        note("minio_restored")
        code, retry = request(base, f"/api/v1/jobs/{job_id}/retry", {})
        if code != 202 or retry.get("status") != "QUEUED":
            raise RuntimeError(f"Explicit retry returned HTTP {code}")
        note("retry_requested")
        recovered = wait_job(base, job_id, "SUCCEEDED", deadline)
        if not (recovered.get("result") or {}).get("input_sha256"):
            raise RuntimeError("Recovered result lacks input lineage")
        note("result_persisted")
        final_bundle = from_api(base, job_id, os.environ.get("VIDEO_API_KEY", ""))
        write_json(args.output_dir / "recovered_job.json", final_bundle)
        _, final_attempts = request(base, f"/api/v1/jobs/{job_id}/attempts")
        if [item["status"] for item in final_attempts] != ["FAILED", "SUCCEEDED"]:
            raise RuntimeError("Expected failed and successful durable attempts")
        report = {"schema_version": "minio-incident-v1",
                  "purpose": "controlled local MinIO interruption with CPU inference",
                  "job_id_sha256": hashlib.sha256(job_id.encode()).hexdigest(),
                  "input_sha256": hashlib.sha256(SAMPLE.encode()).hexdigest(),
                  "timeline": timeline,
                  "first_attempt_error_code": "dependency",
                  "first_attempt_stage": stage,
                  "attempt_statuses": [item["status"] for item in final_attempts],
                  "failure_bundle_sha256": bundle["bundle_sha256"],
                  "recovery_bundle_sha256": final_bundle["bundle_sha256"],
                  "limits": ["One local MinIO outage and CPU job; no GPU or decoder claim.",
                             "Stage is from one job-correlated structured worker log, not the ordinary API exporter."]}
    finally:
        restore_errors = []
        for service in SERVICES:
            try:
                compose("start", service)
            except Exception as error:
                restore_errors.append(f"{service}: {type(error).__name__}")
        if not restore_errors:
            try:
                if not set(SERVICES).issubset(running_services()):
                    raise RuntimeError("A restored container is not running")
                wait_ready(base, time.monotonic() + 30)
                note("services_restored")
            except Exception as error:
                restore_errors.append(f"readiness: {type(error).__name__}")
        write_json(args.output_dir / "run_state.json", {
            "schema_version": "minio-incident-run-state-v1",
            "job_id_sha256": hashlib.sha256(job_id.encode()).hexdigest() if job_id else None,
            "timeline": timeline,
            "completed": "report" in locals() and not restore_errors,
            "restoration_errors": restore_errors,
        })
        if restore_errors:
            raise RuntimeError("Could not restore services: " + ", ".join(restore_errors))
        if "report" in locals():
            report["timeline"] = timeline
            write_json(args.output_dir / "incident.json", report)
    print(f"PASS real MinIO interruption, durable failure and recovered result: {job_id}")
    print(f"Evidence: {args.output_dir / 'incident.json'}")


if __name__ == "__main__":
    main()
