"""Check a deployed local release, one real GPU job, and preserved results."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from scripts.admission_demo import request
from scripts.service_smoke import wait_for_job
from scripts.serving_load import multipart
from src.lineage import canonical_hash


def get_json(base, path, data=None, headers=None):
    code, body = request(base + path, data, headers)
    return code, json.loads(body)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--expected-release")
    parser.add_argument("--legacy-release", action="store_true")
    parser.add_argument("--preserve", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if (args.expected_release is None) == (not args.legacy_release):
        parser.error("Specify exactly one of --expected-release and --legacy-release")
    base = "http://127.0.0.1:8000"
    code, live = get_json(base, "/health/live")
    if code != 200 or live.get("status") != "ok":
        raise RuntimeError("API is not live")
    if args.legacy_release:
        if "release_id" in live:
            raise RuntimeError(f"Expected previous image without release_id, got {live}")
    elif live.get("release_id") != args.expected_release:
        raise RuntimeError(f"Wrong deployed release: {live}")
    code, ready = get_json(base, "/health/ready")
    if code != 200 or ready.get("status") != "ok":
        raise RuntimeError(f"Release is not ready: {ready}")
    preserved = []
    for job_id in args.preserve:
        code, job = get_json(base, "/api/v1/jobs/" + job_id)
        if code != 200 or job["status"] != "SUCCEEDED" or not job.get("result"):
            raise RuntimeError(f"Persisted result unavailable: {job_id}")
        preserved.append({"job_id": job_id, "result_hash": canonical_hash(job["result"])})
    video = args.video.read_bytes()
    body, content_type = multipart(video, None)
    code, submission = get_json(base, "/api/v1/jobs", body,
                                {"Content-Type": content_type})
    if code != 202:
        raise RuntimeError(f"Release did not accept a job: {code} {submission}")
    job = wait_for_job(base, submission["job_id"], args.timeout)
    if job["status"] != "SUCCEEDED" or (job.get("result") or {}).get("model_version") in {None, "fake"}:
        raise RuntimeError(f"Release GPU job failed: {job['status']}")
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "live": live,
              "input_sha256": hashlib.sha256(video).hexdigest(),
              "preserved": preserved, "new_job_id": job["job_id"],
              "new_result_hash": canonical_hash(job["result"]),
              "model_revision": job["result"].get("model_revision"),
              "lineage": job["result"].get("lineage"),
              "timings": job["result"].get("timings"), "passed": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS release probe: {job['job_id']}; preserved {len(preserved)} results")
    print(f"Evidence: {args.output}")


if __name__ == "__main__":
    main()
