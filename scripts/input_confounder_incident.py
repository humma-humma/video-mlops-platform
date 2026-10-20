"""Run two registered CPU-input faults and restore both synthetic objects."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import time
from urllib.request import ProxyHandler, build_opener
from uuid import UUID

from scripts.diagnostic_workbench import write_json
from scripts.model_artifact_incident import active_cpu_jobs, command
from scripts.result_loss_incident import object_bytes, request
from src.diagnostics import NoRedirect, diagnose, digest, from_api, read_json


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "diagnostics" / "input-confounder-live"
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.gpu.yml"]
SAMPLE = "A synthetic service classifies a short technology sentence."


def submit(opener, base, key):
    status, response = request(opener, base, "/api/v1/deployments/text-topic-v1/jobs", key,
                               {"text": SAMPLE})
    if status != 202:
        raise RuntimeError(f"CPU submission returned HTTP {status}")
    return str(UUID(response["job_id"]))


def settle(opener, base, key, job_id, deadline):
    while time.monotonic() < deadline:
        status, job = request(opener, base, "/api/v1/jobs/" + job_id, key)
        if status != 200:
            raise RuntimeError(f"Job read returned HTTP {status}")
        if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return job
        time.sleep(1)
    raise TimeoutError("Synthetic CPU job did not settle")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    if args.base_url not in {"http://127.0.0.1:8000", "http://localhost:8000"}:
        parser.error("Only the local demo API is accepted")
    output = args.output_dir.resolve()
    if any((output / name).exists() for name in (
            "run_state.json", "ledger.json", "incident.json", "undecodable_input.json", "missing_input.json")):
        raise FileExistsError("Recorded evidence already exists; use a fresh output directory")
    protocol, protocol_hash = read_json(output / "protocol.json")
    cases, cases_hash = read_json(output / "cases.json")
    rules_hash = digest((ROOT / "src" / "diagnostics.py").read_bytes())
    if protocol["rules_sha256"] != rules_hash:
        raise RuntimeError("Diagnostic rules differ from the registered version")
    expected = protocol["cases"]
    if {case["id"]: case["expected"] for case in cases["cases"]} != {
            name: spec["expected_diagnosis"] for name, spec in expected.items()}:
        raise RuntimeError("Case manifest differs from registered labels")
    key = os.environ.get("VIDEO_API_KEY", "")
    opener = build_opener(ProxyHandler({}), NoRedirect)
    status, health = request(opener, args.base_url, "/health/ready", key)
    if status != 200 or health.get("status") != "ok":
        raise RuntimeError("Local service is not ready")
    active_cpu_jobs(opener, args.base_url, key)
    container = command([*COMPOSE, "ps", "-q", "cpu-worker"])
    if not container:
        raise RuntimeError("CPU worker is not running")
    import boto3
    from botocore.config import Config
    bucket = os.environ.get("VIDEO_S3_BUCKET", "video-artifacts")
    s3 = boto3.client("s3", endpoint_url="http://127.0.0.1:9000", region_name="us-east-1",
                      aws_access_key_id=os.environ.get("VIDEO_S3_ACCESS_KEY_ID", "minio"),
                      aws_secret_access_key=os.environ.get("VIDEO_S3_SECRET_ACCESS_KEY", "miniosecret"),
                      config=Config(s3={"addressing_style": "path"}, connect_timeout=3, read_timeout=10,
                                    retries={"max_attempts": 2, "mode": "standard"}))
    s3.head_bucket(Bucket=bucket)
    registered_commit = command(["git", "rev-parse", "HEAD"])
    jobs = {}
    originals = {}
    changed = set()
    restored = {}
    worker_started = False
    try:
        command([*COMPOSE, "stop", "cpu-worker"], timeout=120)
        for name in ("undecodable_text_input", "missing_cpu_input"):
            job_id = submit(opener, args.base_url, key)
            jobs[name] = job_id
            object_key = f"inputs/{job_id}/input.txt"
            originals[name] = object_bytes(s3, bucket, object_key)
            if originals[name] != SAMPLE.encode("utf-8"):
                raise RuntimeError("New input object differs from the synthetic sample")
            job_status, queued = request(opener, args.base_url, "/api/v1/jobs/" + job_id, key)
            if job_status != 200 or queued["status"] != "QUEUED":
                raise RuntimeError("CPU worker processed a job before the intervention")
        changed.add("undecodable_text_input")
        s3.put_object(Bucket=bucket, Key=f"inputs/{jobs['undecodable_text_input']}/input.txt",
                      Body=b"\xff\xfe")
        changed.add("missing_cpu_input")
        s3.delete_object(Bucket=bucket, Key=f"inputs/{jobs['missing_cpu_input']}/input.txt")
        command(["docker", "start", container], timeout=120)
        worker_started = True
        deadline = time.monotonic() + 90
        for name, job_id in jobs.items():
            job = settle(opener, args.base_url, key, job_id, deadline)
            if job["status"] != expected[name]["expected_status"]:
                raise RuntimeError(f"{name} ended {job['status']}")
    finally:
        for name in changed:
            object_key = f"inputs/{jobs[name]}/input.txt"
            try:
                s3.put_object(Bucket=bucket, Key=object_key, Body=originals[name])
                restored[name] = digest(object_bytes(s3, bucket, object_key)) == digest(originals[name])
            except Exception:
                restored[name] = False
        if not worker_started:
            try:
                command(["docker", "start", container], timeout=120)
                worker_started = True
            except Exception:
                pass
        write_json(output / "run_state.json", {
            "schema_version": "cpu-input-challenge-restoration-v1",
            "job_id_sha256": {name: digest(job_id.encode()) for name, job_id in jobs.items()},
            "input_sha256": {name: digest(raw) for name, raw in originals.items()},
            "object_restored_exactly": restored,
            "cpu_worker_started": worker_started,
        })
    if set(restored) != set(jobs) or not all(restored.values()) or not worker_started:
        raise RuntimeError("Input objects or CPU worker were not fully restored; inspect run_state.json")
    bundles = {}
    for name, job_id in jobs.items():
        bundle = from_api(args.base_url, job_id, key)
        attempt = bundle["observations"]["attempts"]
        if (len(attempt) != 1 or attempt[0]["error_code"] != expected[name]["expected_attempt_code"]
                or bundle["observations"].get("failure_stage") != expected[name]["expected_failure_stage"]):
            raise RuntimeError(f"{name} did not produce the registered attempt evidence")
        bundles[name] = bundle
        filename = next(case["bundle"] for case in cases["cases"] if case["id"] == name)
        write_json(output / filename, bundle)
    control_id = submit(opener, args.base_url, key)
    control = settle(opener, args.base_url, key, control_id, time.monotonic() + 60)
    if control["status"] != "SUCCEEDED":
        raise RuntimeError(f"Restored-worker control ended {control['status']}")
    write_json(output / "control_job.json", from_api(args.base_url, control_id, key))
    predictions = {name: diagnose(bundle)["diagnosis"] for name, bundle in bundles.items()}
    ledger = {
        "schema_version": "cpu-input-challenge-v1",
        "protocol_sha256": protocol_hash,
        "case_manifest_sha256": cases_hash,
        "rules_sha256": rules_hash,
        "registered_commit": registered_commit,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "job_id_sha256": {name: digest(job_id.encode()) for name, job_id in jobs.items()},
        "input_sha256": {name: digest(raw) for name, raw in originals.items()},
        "attempt_codes": {name: bundle["observations"]["attempts"][0]["error_code"]
                          for name, bundle in bundles.items()},
        "failure_stages": {name: bundle["observations"].get("failure_stage")
                           for name, bundle in bundles.items()},
        "predictions": predictions,
        "control_status": control["status"],
        "limits": protocol["limits"],
    }
    write_json(output / "ledger.json", ledger)
    write_json(output / "incident.json", {
        "schema_version": "cpu-input-challenge-v1",
        "protocol_sha256": protocol_hash,
        "ledger_sha256": digest((output / "ledger.json").read_bytes()),
        "run_state_sha256": digest((output / "run_state.json").read_bytes()),
        "bundle_sha256": {name: bundle["bundle_sha256"] for name, bundle in bundles.items()},
        "predictions": predictions,
    })
    print("PASS new CPU input faults, exact object restoration and successful control job")
    print(f"Evidence: {output / 'incident.json'}")


if __name__ == "__main__":
    main()
