"""Bounded closed-loop measurement of the asynchronous inference API."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4


TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def summarize(rows, elapsed):
    completed = [r for r in rows if r["outcome"] == "SUCCEEDED"]
    def distribution(key):
        values = [r[key] for r in completed if r.get(key) is not None]
        return {"count": len(values), "p50": percentile(values, .5),
                "p95": percentile(values, .95)}
    return {"attempted": len(rows), "succeeded": len(completed),
            "failed": sum(r["outcome"] == "FAILED" for r in rows),
            "cancelled": sum(r["outcome"] == "CANCELLED" for r in rows),
            "timeouts": sum(r["outcome"] == "TIMEOUT" for r in rows),
            "client_errors": sum(r["outcome"] == "CLIENT_ERROR" for r in rows),
            "elapsed_seconds": elapsed,
            "successful_jobs_per_minute": len(completed) * 60 / elapsed if elapsed > 0 else None,
            "successful_submission_seconds": distribution("submission_seconds"),
            "successful_completion_observed_seconds": distribution("completion_observed_seconds"),
            "successful_initial_queue_seconds": distribution("initial_queue_seconds")}


def multipart(video, transcript):
    boundary = uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="video"; '
            'filename="serving-load.mp4"\r\nContent-Type: video/mp4\r\n\r\n').encode() + video + b"\r\n"
    if transcript is not None:
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="transcript"\r\n\r\n').encode()
        body += transcript + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def request_json(url, *, data=None, headers=None, timeout=30):
    headers = dict(headers or {})
    if os.environ.get("VIDEO_API_KEY"):
        headers["X-API-Key"] = os.environ["VIDEO_API_KEY"]
    with urlopen(Request(url, data=data, headers=headers), timeout=timeout) as response:
        return response.status, json.load(response)


def measure_job(base, body, content_type, timeout, poll_interval, emit):
    start = time.monotonic()
    row = {"request_id": uuid4().hex, "job_id": None, "outcome": "CLIENT_ERROR"}
    try:
        status, submission = request_json(base + "/api/v1/jobs", data=body,
            headers={"Content-Type": content_type, "Idempotency-Key": row["request_id"]},
            timeout=min(30, timeout))
        row["job_id"] = submission.get("job_id")
        row["submission_seconds"] = time.monotonic() - start
        if status != 202 or not row["job_id"]:
            raise ValueError("Submission did not return a job")
        emit({"event": "accepted", **row, "outcome": "ACCEPTED"})
        deadline = start + timeout
        while time.monotonic() < deadline:
            _, job = request_json(base + "/api/v1/jobs/" + row["job_id"],
                                  timeout=min(30, max(.1, deadline - time.monotonic())))
            if job["status"] in TERMINAL:
                row.update(outcome=job["status"], completion_observed_seconds=time.monotonic() - start)
                result = job.get("result") or {}
                row.update({key: result.get(key) for key in
                            ("model_version", "model_revision", "model_instance_id", "lineage", "timings")})
                try:
                    _, attempts = request_json(base + "/api/v1/jobs/" + row["job_id"] + "/attempts")
                    row["attempts"] = attempts
                    if attempts and attempts[0].get("started_at") and job.get("created_at"):
                        row["initial_queue_seconds"] = max(0, (
                            datetime.fromisoformat(attempts[0]["started_at"].replace("Z", "+00:00")) -
                            datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))).total_seconds())
                except Exception as error:
                    row["attempt_evidence_error"] = type(error).__name__
                break
            time.sleep(min(poll_interval, max(0, deadline - time.monotonic())))
        else:
            row["outcome"] = "TIMEOUT"
    except Exception as error:
        # Do not persist response bodies, credentials, transcripts or summaries.
        row["client_error_type"] = type(error).__name__
        row["http_status"] = getattr(error, "code", None)
    row["client_elapsed_seconds"] = time.monotonic() - start
    emit({"event": "finished", **row})
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--poll-interval", type=float, default=1)
    parser.add_argument("--output-root", type=Path, default=Path("data/outputs/serving-load"))
    args = parser.parse_args(argv)
    client_source = Path(__file__).read_bytes()
    if not 1 <= args.concurrency <= args.jobs <= 20 or args.timeout <= 0 or args.poll_interval <= 0:
        parser.error("Require 1 <= concurrency <= jobs <= 20 and positive timeouts/intervals")
    parsed = urlsplit(args.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("Use an HTTP(S) base URL without embedded credentials, query or fragment")
    video = args.video.read_bytes()
    transcript = args.transcript.read_bytes() if args.transcript else None
    body, content_type = multipart(video, transcript)
    base = args.base_url.rstrip("/")
    code, health = request_json(base + "/health/ready")
    if code != 200 or health["status"] != "ok":
        raise RuntimeError("Service is not ready")
    output = args.output_root / uuid4().hex
    output.mkdir(parents=True)
    (output / "serving_load.py").write_bytes(client_source)
    lock = threading.Lock()
    with (output / "jobs.jsonl").open("w", encoding="utf-8") as journal:
        def emit(record):
            with lock:
                journal.write(json.dumps(record) + "\n")
                journal.flush()
        started_at = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(measure_job, base, body, content_type, args.timeout,
                                   args.poll_interval, emit) for _ in range(args.jobs)]
            rows = [f.result() for f in as_completed(futures)]
        elapsed = time.monotonic() - start
    report = {"schema_version": "1", "purpose": "bounded serving measurement; not capacity/SLO acceptance",
              "started_at": started_at, "base_url": base,
              "client_source_sha256": hashlib.sha256(client_source).hexdigest(),
              "input_sha256": hashlib.sha256(video).hexdigest(),
              "transcript_sha256": hashlib.sha256(transcript).hexdigest() if transcript is not None else None,
              "jobs": args.jobs, "client_concurrency": args.concurrency,
              "per_job_timeout_seconds": args.timeout, "poll_interval_seconds": args.poll_interval,
              "load_model": "closed loop: each client waits for a terminal result before submitting its next job",
              "limits": ["Completion latency includes upload and polling delay; not pure GPU inference time.",
                         "Queue timing uses first attempt start minus job creation, including dispatch overhead.",
                         "No worker restart or warmup is forced; model_load timings describe observed state.",
                         "Timeout/client error does not cancel a server job; accepted IDs remain in journal.",
                         "Tiny repeated-input runs do not establish sustained capacity or representative P95.",
                         "No GPU utilization sampling or cloud cost measurement is performed by this runner."],
              "metrics": summarize(rows, elapsed), "runs": rows}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report: {output / 'report.json'}", flush=True)
    print(json.dumps(report["metrics"], indent=2), flush=True)
    return 0 if all(r["outcome"] == "SUCCEEDED" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
