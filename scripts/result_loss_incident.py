"""Delete and restore only a newly created CPU job's result object."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import UUID

from scripts.diagnostic_workbench import write_json
from src.diagnostics import NoRedirect, canonical, diagnose, digest, from_api, read_json, validate_bundle


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reports" / "diagnostics" / "result-loss-live"
SAMPLE = "A local machine learning service processes a synthetic test sentence."


def request(opener, base, route, api_key, payload=None):
    headers = {"X-API-Key": api_key} if api_key else {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    try:
        response = opener.open(Request(base + route, data=data, headers=headers), timeout=10)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise RuntimeError("API response exceeded evidence bound")
        return response.getcode(), json.loads(raw)


def object_bytes(s3, bucket, key):
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    try:
        raw = body.read(2_000_001)
    finally:
        body.close()
    if len(raw) > 2_000_000:
        raise RuntimeError("Result object exceeded evidence bound")
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if args.base_url not in {"http://127.0.0.1:8000", "http://localhost:8000"}:
        parser.error("This intervention only accepts the local API on port 8000")
    output = args.output_dir.resolve()
    if any((output / name).exists() for name in ("ledger.json", "missing_result.json", "incident.json")):
        raise FileExistsError("Existing incident evidence must not be overwritten")
    protocol, protocol_hash = read_json(output / "protocol.json")
    if protocol["expected"] != "insufficient_evidence":
        raise RuntimeError("Unexpected registered diagnosis")
    registered_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                text=True).strip()
    opener = build_opener(ProxyHandler({}), NoRedirect)
    api_key = os.environ.get("VIDEO_API_KEY", "")
    status, health = request(opener, args.base_url, "/health/live", api_key)
    if status != 200:
        raise RuntimeError("Local API is unavailable")
    release_hash = digest(health["release_id"].encode())

    import boto3
    from botocore.config import Config
    bucket = os.environ.get("VIDEO_S3_BUCKET", "video-artifacts")
    s3 = boto3.client("s3", endpoint_url="http://127.0.0.1:9000", region_name="us-east-1",
                      aws_access_key_id=os.environ.get("VIDEO_S3_ACCESS_KEY_ID", "minio"),
                      aws_secret_access_key=os.environ.get("VIDEO_S3_SECRET_ACCESS_KEY", "miniosecret"),
                      config=Config(s3={"addressing_style": "path"},
                                    connect_timeout=3, read_timeout=10,
                                    retries={"max_attempts": 2, "mode": "standard"}))
    s3.head_bucket(Bucket=bucket)
    status, submitted = request(opener, args.base_url,
                                "/api/v1/deployments/text-topic-v1/jobs", api_key,
                                {"text": SAMPLE})
    if status != 202:
        raise RuntimeError(f"CPU job submission returned HTTP {status}")
    job_id = str(UUID(submitted["job_id"]))
    route = "/api/v1/jobs/" + job_id
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        status, job = request(opener, args.base_url, route, api_key)
        if status != 200:
            raise RuntimeError(f"Initial job read returned HTTP {status}")
        if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break
        time.sleep(1)
    else:
        raise TimeoutError("CPU job did not finish within 60 seconds")
    if job["status"] != "SUCCEEDED":
        raise RuntimeError(f"CPU job ended {job['status']}")
    healthy_bundle = from_api(args.base_url, job_id, api_key)
    if len(healthy_bundle["observations"]["attempts"]) != 1 or healthy_bundle["observations"][
            "attempts"][0]["status"] != "SUCCEEDED":
        raise RuntimeError("Expected one successful attempt")
    key = f"results/{job_id}/attempt-1.json"
    original = object_bytes(s3, bucket, key)
    if json.loads(original) != job["result"]:
        raise RuntimeError("Result object does not match the new job")
    original_hash = digest(original)
    deleted = False
    restored = False
    lost_status = None
    list_status = None
    deleted_at = None
    restored_at = None
    try:
        s3.delete_object(Bucket=bucket, Key=key)
        deleted = True
        deleted_at = datetime.now(timezone.utc).isoformat()
        lost_status, missing = request(opener, args.base_url, route, api_key)
        if lost_status != 503 or missing != {"detail": "Result artifact unavailable"}:
            raise RuntimeError(f"Missing-result read returned HTTP {lost_status}")
        s3.head_bucket(Bucket=bucket)
        status, jobs = request(opener, args.base_url,
                               "/api/v1/jobs?limit=100&deployment_id=text-topic-v1", api_key)
        if status != 200:
            raise RuntimeError("Could not read durable job list")
        list_status = next((item["status"] for item in jobs if item["job_id"] == job_id), None)
        if list_status != "SUCCEEDED":
            raise RuntimeError("Durable job status changed during result loss")
        status, attempts = request(opener, args.base_url, route + "/attempts", api_key)
        if status != 200 or len(attempts) != 1 or attempts[0]["status"] != "SUCCEEDED":
            raise RuntimeError("Attempt history changed during result loss")
    finally:
        if deleted:
            try:
                s3.put_object(Bucket=bucket, Key=key, Body=original)
                restored = digest(object_bytes(s3, bucket, key)) == original_hash
                restored_at = datetime.now(timezone.utc).isoformat()
            finally:
                write_json(output / "run_state.json", {
                    "schema_version": "result-loss-restoration-v1",
                    "job_id_sha256": digest(job_id.encode()),
                    "result_object_sha256": original_hash,
                    "object_restored_exactly": restored,
                })
    if not restored:
        raise RuntimeError("Result object restoration could not be verified")
    restored_status, after = request(opener, args.base_url, route, api_key)
    if restored_status != 200 or after["status"] != "SUCCEEDED" or after["result"] != job["result"]:
        raise RuntimeError("API result did not recover after object restoration")
    status, health_after = request(opener, args.base_url, "/health/live", api_key)
    if status != 200 or digest(health_after["release_id"].encode()) != release_hash:
        raise RuntimeError("API release changed during the intervention")

    ledger = {
        "schema_version": "result-loss-incident-v1",
        "protocol_sha256": protocol_hash,
        "registered_commit": registered_commit,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "result_object_deleted_at": deleted_at,
        "result_object_restored_at": restored_at,
        "job_id_sha256": digest(job_id.encode()),
        "result_object_sha256": original_hash,
        "release_id_sha256": release_hash,
        "submission_status": 202,
        "job_status_before": "SUCCEEDED",
        "read_before": 200,
        "read_during_object_loss": lost_status,
        "bucket_available_during_object_loss": True,
        "job_list_status_during_object_loss": list_status,
        "read_after_restore": restored_status,
        "successful_attempts": 1,
        "result_object_restored_exactly": restored,
        "limits": protocol["limits"],
    }
    write_json(output / "ledger.json", ledger)
    ledger_hash = digest((output / "ledger.json").read_bytes())
    bundle = deepcopy(healthy_bundle)
    bundle["source_kind"] = "live_api_plus_controlled_event"
    bundle["source_sha256"]["report"] = ledger_hash
    bundle["observations"]["result_read_http_status"] = lost_status
    bundle["bundle_sha256"] = digest(canonical({key: value for key, value in bundle.items()
                                                if key != "bundle_sha256"}))
    validate_bundle(bundle)
    write_json(output / "missing_result.json", bundle)
    result = diagnose(bundle)
    if result["diagnosis"] != protocol["expected"]:
        raise RuntimeError(f"Prospective diagnostic miss: {result['diagnosis']}")
    write_json(output / "incident.json", {
        "schema_version": "result-loss-incident-v1",
        "protocol_sha256": protocol_hash,
        "ledger_sha256": ledger_hash,
        "bundle_sha256": bundle["bundle_sha256"],
        "run_state_sha256": digest((output / "run_state.json").read_bytes()),
        "registered_commit": registered_commit,
        "diagnosis": result["diagnosis"],
    })
    print("PASS result object loss: API 503 with durable success, then exact restoration; diagnosis abstained")
    print(f"Evidence: {output / 'incident.json'}")


if __name__ == "__main__":
    main()
