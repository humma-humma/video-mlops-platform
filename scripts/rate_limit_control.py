"""Exercise the real API rate-limit middleware without touching the deployed service."""

import argparse
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.diagnostics import diagnose, finish_bundle
from src.service import api


def write_json(path: Path, value: dict) -> bytes:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=Path("reports/diagnostics/rate-limit-control"))
    args = parser.parse_args(argv)
    previous_limit = api.settings.request_rate_limit_per_minute
    try:
        api.recent_requests.clear()
        api.settings.request_rate_limit_per_minute = 1
        client = TestClient(api.app)
        try:
            first = client.get("/openapi.json")
            second = client.get("/openapi.json")
        finally:
            client.close()
        if (first.status_code, second.status_code, second.headers.get("retry-after")) != (
                200, 429, "60"):
            raise RuntimeError("Unexpected isolated rate-limit behavior")
    finally:
        api.settings.request_rate_limit_per_minute = previous_limit
        api.recent_requests.clear()

    ledger = {
        "schema_version": "rate-limit-control-v1",
        "purpose": "isolated API middleware 429 confounder",
        "execution": "in-process TestClient; deployed service unchanged",
        "route": "/openapi.json",
        "configured_requests_per_minute": 1,
        "http_statuses": [first.status_code, second.status_code],
        "retry_after_seconds": int(second.headers["retry-after"]),
        "limits": [
            "No GPU job or capacity measurement was involved.",
            "This is an isolated middleware replay, not a live deployment incident."
        ],
    }
    ledger_raw = write_json(args.output_dir / "ledger.json", ledger)
    observations = {
        "status": None,
        "attempts": [],
        "events": [],
        "admission": {"capacity": None, "http_statuses": [second.status_code],
                      "after_drain_status": None},
        "timings_seconds": {},
        "model_revision": None,
        "input_sha256": None,
    }
    bundle = finish_bundle("isolated_replay", {
        "report": hashlib.sha256(ledger_raw).hexdigest()}, observations)
    result = diagnose(bundle)
    if result["diagnosis"] != "insufficient_evidence":
        raise RuntimeError(f"429 without capacity caused a false GPU diagnosis: {result}")
    write_json(args.output_dir / "rate_limit.json", bundle)
    print("PASS isolated request-rate 429; GPU-capacity diagnosis abstained")
    print(f"Evidence: {args.output_dir / 'ledger.json'}")


if __name__ == "__main__":
    main()
