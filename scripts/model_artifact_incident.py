"""Hide the local CPU model artifact for one new job, then restore it exactly."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.request import ProxyHandler, build_opener
from uuid import UUID

from scripts.diagnostic_workbench import write_json
from scripts.result_loss_incident import request
from src.diagnostics import NoRedirect, diagnose, digest, from_api, read_json


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reports" / "diagnostics" / "model-artifact-live"
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.gpu.yml"]
MODEL = "/app/src/service/model_artifacts/text_topic_v1.json"
HIDDEN = MODEL + ".incident-hidden"
SAMPLE = "A synthetic server processes Python code."


def command(args, *, timeout=60):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Command failed: {args[0]} {args[1]} ({result.returncode}): {result.stderr.strip()[:300]}")
    return result.stdout.strip()


def container_file_exists(container, path):
    result = subprocess.run(["docker", "exec", "-u", "0", container, "test", "-e", path],
                            cwd=ROOT, capture_output=True, text=True, timeout=15)
    if result.returncode not in (0, 1):
        raise RuntimeError("Could not inspect CPU worker artifact path")
    return result.returncode == 0


def active_cpu_jobs(opener, base, api_key):
    for offset in range(0, 1000, 100):
        status, page = request(opener, base, f"/api/v1/jobs?deployment_id=text-topic-v1&limit=100&offset={offset}", api_key)
        if status != 200 or not isinstance(page, list):
            raise RuntimeError("CPU job inventory unavailable")
        if any(job["status"] in {"PENDING", "QUEUED", "RUNNING"} for job in page):
            raise RuntimeError("Wait until no CPU jobs are outstanding")
        if len(page) < 100:
            return
    raise RuntimeError("CPU job inventory exceeds the bounded preflight")


def submit_and_wait(opener, base, api_key):
    status, submitted = request(opener, base, "/api/v1/deployments/text-topic-v1/jobs", api_key,
                                {"text": SAMPLE})
    if status != 202:
        raise RuntimeError(f"Text submission returned HTTP {status}")
    job_id = str(UUID(submitted["job_id"]))
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        status, job = request(opener, base, "/api/v1/jobs/" + job_id, api_key)
        if status != 200:
            raise RuntimeError(f"Job read returned HTTP {status}")
        if job["status"] in {"FAILED", "SUCCEEDED", "CANCELLED"}:
            return job_id, job
        time.sleep(1)
    raise TimeoutError("Text job did not finish within 60 seconds")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if args.base_url not in {"http://127.0.0.1:8000", "http://localhost:8000"}:
        parser.error("Only the local demo API is accepted")
    output = args.output_dir.resolve()
    for name in ("run_state.json", "ledger.json", "failed_job.json", "incident.json"):
        if (output / name).exists():
            raise FileExistsError("Incident evidence already exists; use a fresh output directory")
    protocol, protocol_hash = read_json(output / "protocol.json")
    cases, _ = read_json(output / "cases.json")
    expected = protocol["expected_observations_after_repair"]
    if cases["cases"][0]["expected"] != expected["diagnosis"]:
        raise RuntimeError("Registered case and protocol disagree")
    api_key = os.environ.get("VIDEO_API_KEY", "")
    opener = build_opener(ProxyHandler({}), NoRedirect)
    status, ready = request(opener, args.base_url, "/health/ready", api_key)
    if status != 200 or ready.get("status") != "ok":
        raise RuntimeError("Local service is not ready")
    active_cpu_jobs(opener, args.base_url, api_key)
    container = command([*COMPOSE, "ps", "-q", "cpu-worker"])
    if not re.fullmatch(r"[0-9a-f]{12,64}", container):
        raise RuntimeError("Expected one running CPU-worker container")
    original_hash = command(["docker", "exec", "-u", "0", container, "sha256sum", MODEL]).split()[0]
    if not re.fullmatch(r"[0-9a-f]{64}", original_hash):
        raise RuntimeError("Could not verify packaged model artifact")
    if container_file_exists(container, HIDDEN):
        raise RuntimeError("Hidden artifact already exists; inspect the CPU worker first")
    registered_commit = command(["git", "rev-parse", "HEAD"])
    hidden = False
    restored = False
    failed_id = None
    try:
        hidden = True
        command(["docker", "exec", "-u", "0", container, "mv", MODEL, HIDDEN])
        command([*COMPOSE, "restart", "cpu-worker"], timeout=120)
        failed_id, failed_job = submit_and_wait(opener, args.base_url, api_key)
        if failed_job["status"] != expected["failed_job_status"]:
            raise RuntimeError(f"Injected job ended {failed_job['status']}")
        failed_bundle = from_api(args.base_url, failed_id, api_key)
        attempts = failed_bundle["observations"]["attempts"]
        if len(attempts) != 1 or attempts[0]["error_code"] != expected["attempt_error_code"]:
            raise RuntimeError(f"Unexpected injected attempt codes: {[a['error_code'] for a in attempts]}")
        diagnosis = diagnose(failed_bundle)
        if diagnosis["diagnosis"] != expected["diagnosis"]:
            raise RuntimeError(f"Unexpected diagnosis: {diagnosis['diagnosis']}")
    finally:
        if hidden:
            try:
                if container_file_exists(container, HIDDEN):
                    command(["docker", "exec", "-u", "0", container, "mv", HIDDEN, MODEL])
                restored_hash = command(["docker", "exec", "-u", "0", container, "sha256sum", MODEL]).split()[0]
                restored = restored_hash == original_hash
                command([*COMPOSE, "restart", "cpu-worker"], timeout=120)
            finally:
                write_json(output / "run_state.json", {
                    "schema_version": "model-artifact-restoration-v1",
                    "failed_job_id_sha256": digest(failed_id.encode()) if failed_id else None,
                    "model_artifact_sha256": original_hash,
                    "artifact_restored_exactly": restored,
                })
    if not restored:
        raise RuntimeError("CPU model artifact restoration could not be verified")
    active_cpu_jobs(opener, args.base_url, api_key)
    control_id, control_job = submit_and_wait(opener, args.base_url, api_key)
    if control_job["status"] != expected["control_job_status"]:
        raise RuntimeError(f"Restored-worker control ended {control_job['status']}")
    write_json(output / "failed_job.json", failed_bundle)
    control_bundle = from_api(args.base_url, control_id, api_key)
    write_json(output / "control_job.json", control_bundle)
    ledger = {
        "schema_version": "model-artifact-incident-v1",
        "protocol_sha256": protocol_hash,
        "registered_commit": registered_commit,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "failed_job_id_sha256": digest(failed_id.encode()),
        "control_job_id_sha256": digest(control_id.encode()),
        "model_artifact_sha256": original_hash,
        "injected_attempt_error_code": attempts[0]["error_code"],
        "diagnosis": diagnosis["diagnosis"],
        "control_status": control_job["status"],
        "artifact_restored_exactly": restored,
        "limits": protocol["limits"],
    }
    write_json(output / "ledger.json", ledger)
    write_json(output / "incident.json", {
        "schema_version": "model-artifact-incident-v1",
        "protocol_sha256": protocol_hash,
        "ledger_sha256": digest((output / "ledger.json").read_bytes()),
        "failure_bundle_sha256": failed_bundle["bundle_sha256"],
        "control_bundle_sha256": control_bundle["bundle_sha256"],
        "run_state_sha256": digest((output / "run_state.json").read_bytes()),
        "diagnosis": diagnosis["diagnosis"],
    })
    print("PASS CPU model artifact failure distinguished from missing job input; artifact restored")
    print(f"Evidence: {output / 'incident.json'}")


if __name__ == "__main__":
    main()
