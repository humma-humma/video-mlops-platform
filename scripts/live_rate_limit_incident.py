"""Bounded read-only rate-limit probe against the running local API."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from src.diagnostics import NoRedirect, diagnose, digest, finish_bundle, metrics_snapshot, read_json, validate_bundle
from scripts.diagnostic_workbench import write_json


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reports" / "diagnostics" / "rate-limit-live"


def get(opener, base: str, route: str):
    request = Request(base + route, method="GET")
    try:
        response = opener.open(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        limit = 2_000_000 if route == "/metrics" else 2_000
        return response.getcode(), response.headers.get("Retry-After"), response.read(limit).decode("utf-8")


def snapshot(opener, base: str):
    status, _, body = get(opener, base, "/health/live")
    if status != 200:
        raise RuntimeError("API liveness unavailable")
    release = json.loads(body)["release_id"]
    status, _, body = get(opener, base, "/metrics")
    if status != 200:
        raise RuntimeError("API metrics unavailable or rate-limited")
    metrics = metrics_snapshot(body)
    if metrics.get("video_jobs_outstanding") != 0 or metrics.get("video_job_capacity", 0) < 1:
        raise RuntimeError("GPU capacity snapshot is missing or jobs are outstanding")
    return {"release_id_sha256": digest(release.encode()),
            "gpu_jobs_outstanding": int(metrics["video_jobs_outstanding"]),
            "gpu_job_capacity": int(metrics["video_job_capacity"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if args.base_url not in {"http://127.0.0.1:8000", "http://localhost:8000"}:
        parser.error("This probe only accepts the local API on port 8000")
    output_dir = args.output_dir.resolve()
    protocol, protocol_hash = read_json(output_dir / "protocol.json")
    if protocol["expected"] != "insufficient_evidence" or protocol["route"] != "/openapi.json":
        raise RuntimeError("Unexpected pre-registered protocol")
    registered_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                text=True).strip()
    opener = build_opener(ProxyHandler({}), NoRedirect)
    before = snapshot(opener, args.base_url)
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    counts = Counter()
    limited_retry_after = None
    for _ in range(protocol["max_requests_to_limit"]):
        if time.monotonic() - started > protocol["max_seconds_to_limit"]:
            raise RuntimeError("Rate limit was not reached within the pre-registered time bound")
        status, retry_after, body = get(opener, args.base_url, protocol["route"])
        counts[status] += 1
        if status == 429:
            if retry_after != "60" or json.loads(body) != {"detail": "Request rate limit exceeded"}:
                raise RuntimeError("429 did not come from the expected request-rate middleware")
            limited_retry_after = int(retry_after)
            break
        if status != 200:
            raise RuntimeError(f"Unexpected probe status {status}")
    if not counts[200] or limited_retry_after is None:
        raise RuntimeError("Expected a 200-to-429 transition within the request bound")
    if get(opener, args.base_url, "/health/live")[0] != 200:
        raise RuntimeError("Excluded liveness route was not available during the limit")
    deadline = time.monotonic() + protocol["recovery_deadline_seconds"]
    recovered = False
    while time.monotonic() < deadline:
        time.sleep(5)
        status, _, _ = get(opener, args.base_url, protocol["route"])
        if status == 200:
            recovered = True
            break
        if status != 429:
            raise RuntimeError(f"Unexpected recovery status {status}")
    if not recovered:
        raise RuntimeError("API did not recover within the pre-registered bound")
    after = snapshot(opener, args.base_url)
    if before["release_id_sha256"] != after["release_id_sha256"]:
        raise RuntimeError("API release changed during the probe")

    ledger = {
        "schema_version": "live-rate-limit-incident-v1",
        "protocol_sha256": protocol_hash,
        "registered_commit": registered_commit,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "route": protocol["route"],
        "method": "GET",
        "probe_status_counts_to_limit": dict(sorted(counts.items())),
        "retry_after_seconds": limited_retry_after,
        "limited_response_kind": "request_rate_limit_exceeded",
        "liveness_during_limit": 200,
        "recovered_probe_status": 200,
        "before": before,
        "after": after,
        "limits": protocol["limits"],
    }
    write_json(output_dir / "ledger.json", ledger)
    ledger_hash = digest((output_dir / "ledger.json").read_bytes())
    bundle = finish_bundle("live_http_probe", {"report": ledger_hash}, {
        "status": None, "attempts": [], "events": [],
        "admission": {"capacity": None, "http_statuses": [429], "after_drain_status": None},
        "timings_seconds": {}, "input_sha256": None, "model_revision": None,
    })
    validate_bundle(bundle)
    write_json(output_dir / "rate_limit.json", bundle)
    result = diagnose(bundle)
    if result["diagnosis"] != protocol["expected"]:
        raise RuntimeError(f"Prospective diagnostic miss: {result['diagnosis']}")
    write_json(output_dir / "incident.json", {
        "schema_version": "live-rate-limit-incident-v1",
        "protocol_sha256": protocol_hash,
        "ledger_sha256": ledger_hash,
        "bundle_sha256": bundle["bundle_sha256"],
        "diagnosis": result["diagnosis"],
        "registered_commit": registered_commit,
    })
    print(f"PASS deployed API request-rate 429 and recovery; diagnosis abstained ({counts[200]} accepted probes)")
    print(f"Evidence: {output_dir / 'incident.json'}")


if __name__ == "__main__":
    main()
