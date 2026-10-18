"""Submit healthy and damaged synthetic MP4s to the real local GPU service."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from scripts.diagnostic_workbench import write_json
from src.diagnostics import compare, diagnose, diagnose_pair, from_api


ROOT = Path(__file__).resolve().parents[1]
OPENER = build_opener(ProxyHandler({}))


def command(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=30)


def make_fixtures(work: Path) -> tuple[Path, Path, dict]:
    work.mkdir(parents=True, exist_ok=True)
    healthy = work / "healthy.mp4"
    damaged = work / "damaged.mp4"
    generated = command("ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "testsrc=size=224x224:rate=2:duration=3",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                        str(healthy))
    if generated.returncode:
        raise RuntimeError("Could not generate the synthetic healthy MP4")
    data = healthy.read_bytes()
    marker = data.find(b"mdat")
    if marker < 8 or data.find(b"mdat", marker + 4) >= 0 or data.find(b"moov") > marker:
        raise RuntimeError("Generated MP4 did not have the expected faststart layout")
    damaged.write_bytes(data[:marker + 4])  # Keep metadata; remove all frame payload.
    for path in (healthy, damaged):
        probe = command("ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
                        "-show_format", "-show_streams", "-of", "json", str(path))
        if probe.returncode:
            raise RuntimeError(f"Metadata inspection rejected {path.name}")
        metadata = json.loads(probe.stdout)
        if not any(stream.get("codec_type") == "video" for stream in metadata.get("streams", [])):
            raise RuntimeError(f"No video stream in {path.name}")
        if not 0 < float(metadata["format"]["duration"]) <= 600:
            raise RuntimeError(f"Invalid duration in {path.name}")
    healthy_decode = command("ffmpeg", "-v", "error", "-i", str(healthy), "-f", "null", "-")
    damaged_decode = command("ffmpeg", "-v", "error", "-i", str(damaged), "-f", "null", "-")
    if healthy_decode.returncode or not damaged_decode.returncode:
        raise RuntimeError("Synthetic video decode control did not behave as expected")
    ledger = {"schema_version": "decoder-incident-fixture-v1",
              "generation": "FFmpeg testsrc 224x224, 2 fps, 3 seconds, H.264 faststart",
              "damage": "All mdat frame payload removed; moov metadata retained",
              "healthy_sha256": hashlib.sha256(data).hexdigest(),
              "damaged_sha256": hashlib.sha256(damaged.read_bytes()).hexdigest(),
              "ffprobe_metadata_accepted": [True, True],
              "ffmpeg_full_decode_succeeded": [True, False]}
    return healthy, damaged, ledger


def request(base: str, path: str, body: bytes | None = None,
            content_type: str | None = None) -> tuple[int, object]:
    headers = {}
    if key := os.environ.get("VIDEO_API_KEY"):
        headers["X-API-Key"] = key
    if content_type:
        headers["Content-Type"] = content_type
    try:
        with OPENER.open(Request(base + path, data=body, headers=headers), timeout=30) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def submit(base: str, path: Path, transcript: str = "") -> str:
    boundary = uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="video"; '
            f'filename="{path.name}"\r\nContent-Type: video/mp4\r\n\r\n').encode()
    body += path.read_bytes() + b"\r\n"
    if transcript:
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="transcript"'
                 f'\r\n\r\n{transcript}\r\n').encode()
    body += f"--{boundary}--\r\n".encode()
    status, result = request(base, "/api/v1/deployments/video-summary-v1/jobs", body,
                             f"multipart/form-data; boundary={boundary}")
    if status != 202:
        raise RuntimeError(f"{path.name} submission returned HTTP {status}")
    return result["job_id"]


def wait_job(base: str, job_id: str, deadline: float) -> dict:
    while time.monotonic() < deadline:
        status, job = request(base, "/api/v1/jobs/" + job_id)
        if status != 200:
            raise RuntimeError(f"Job read returned HTTP {status}")
        if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return job
        time.sleep(2)
    raise TimeoutError("GPU job did not settle before the deadline")


def assert_no_backlog(base: str) -> None:
    for offset in range(0, 1000, 100):
        status, jobs = request(base, f"/api/v1/jobs?limit=100&offset={offset}")
        if status != 200 or not isinstance(jobs, list):
            raise RuntimeError("Could not inspect the current job backlog")
        if any(job["status"] in {"PENDING", "QUEUED", "RUNNING"} for job in jobs):
            raise RuntimeError("Wait for the current job backlog to drain")
        if len(jobs) < 100:
            return
    raise RuntimeError("Job history exceeds the bounded preflight")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--control-video", type=Path, required=True,
                        help="Known video that has previously succeeded on this deployment")
    parser.add_argument("--control-transcript", type=Path)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/diagnostics/decoder-live"))
    args = parser.parse_args(argv)
    base = args.base_url.rstrip("/")
    if base not in {"http://127.0.0.1:8000", "http://localhost:8000"} or args.timeout < 60:
        parser.error("Use the local API and a timeout of at least 60 seconds")
    if not args.control_video.is_file() or args.control_video.suffix.lower() != ".mp4":
        parser.error("--control-video must be an existing MP4")
    status, health = request(base, "/health/ready")
    if status != 200 or health.get("status") != "ok":
        raise RuntimeError("Local service is not ready")
    assert_no_backlog(base)
    _healthy_fixture, damaged, ledger = make_fixtures(ROOT / "data/outputs/decoder-incident-work")
    write_json(args.output_dir / "fixture_ledger.json", ledger)
    print("PASS metadata accepts both files; full decode rejects damaged frames", flush=True)
    deadline = time.monotonic() + args.timeout
    transcript = args.control_transcript.read_text(encoding="utf-8") if args.control_transcript else ""
    healthy_id = submit(base, args.control_video, transcript)
    healthy_job = wait_job(base, healthy_id, deadline)
    if healthy_job["status"] != "SUCCEEDED" or not (healthy_job.get("result") or {}).get("model_revision"):
        raise RuntimeError(f"Healthy GPU control ended {healthy_job['status']}")
    healthy_bundle = from_api(base, healthy_id, os.environ.get("VIDEO_API_KEY", ""))
    if healthy_bundle["observations"]["input_sha256"] != hashlib.sha256(
            args.control_video.read_bytes()).hexdigest():
        raise RuntimeError("Successful GPU control lacks matching input lineage")
    write_json(args.output_dir / "healthy_job.json", healthy_bundle)
    print("PASS known-video GPU control", flush=True)
    damaged_id = submit(base, damaged)
    damaged_job = wait_job(base, damaged_id, deadline)
    damaged_bundle = from_api(base, damaged_id, os.environ.get("VIDEO_API_KEY", ""))
    write_json(args.output_dir / "damaged_job.json", damaged_bundle)
    if damaged_job["status"] != "FAILED":
        raise RuntimeError(f"Damaged GPU job ended {damaged_job['status']} instead of FAILED")
    if [a["error_code"] for a in damaged_bundle["observations"]["attempts"]] != ["inference"]:
        raise RuntimeError("Damaged GPU job did not record one inference failure")
    finding = diagnose(damaged_bundle)
    pair = diagnose_pair(healthy_bundle, damaged_bundle)
    comparison = compare(healthy_bundle, damaged_bundle)
    if (finding["diagnosis"] != "insufficient_evidence"
            or pair["diagnosis"] != "insufficient_evidence"):
        raise RuntimeError("Analyzer made an unsupported diagnosis")
    if comparison["comparable"]:
        raise RuntimeError("Healthy and damaged bytes must not be treated as comparable")
    report = {"schema_version": "decoder-incident-v1",
              "purpose": "controlled damaged-video failure on the local GPU service",
              "fixture_ledger_sha256": hashlib.sha256((args.output_dir / "fixture_ledger.json").read_bytes()).hexdigest(),
              "healthy_bundle_sha256": healthy_bundle["bundle_sha256"],
              "damaged_bundle_sha256": damaged_bundle["bundle_sha256"],
              "healthy_status": healthy_job["status"], "damaged_status": damaged_job["status"],
              "damaged_attempt_codes": [a["error_code"] for a in damaged_bundle["observations"]["attempts"]],
              "single_job_diagnosis": finding["diagnosis"],
              "pair_diagnosis": pair["diagnosis"], "pair_comparable": comparison["comparable"],
              "limits": ["Different input bytes preclude a latency comparison.",
                         "The live API does not expose a decoder-specific worker stage or error code.",
                         "FFmpeg fixture decoding fails; this does not identify the worker's exact decoder exception."]}
    write_json(args.output_dir / "incident.json", report)
    print("PASS damaged GPU job failed; analyzer abstained without decoder-specific evidence", flush=True)
    print(f"Evidence: {args.output_dir / 'incident.json'}")


if __name__ == "__main__":
    main()
