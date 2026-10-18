"""Bounded, content-free evidence bundles for offline service diagnosis."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID


MAX_SOURCE_BYTES = 2_000_000
MAX_RECORDS = 100
SCHEMA = "diagnostic-bundle-v1"
STATUSES = {"PENDING", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"}
ERROR_CODES = {"timeout", "oom", "out_of_memory", "invalid_output", "dependency",
               "storage_error", "missing_input", "inference", "internal"}
TIMING_KEYS = {"model_load", "input_preparation", "summary", "category", "inference_total",
               "input_download", "total"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def read_json(path: Path) -> tuple[dict, str]:
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Evidence source exceeds 2 MB")
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Evidence source must be a JSON object")
    return value, digest(raw)


def limited(value, allowed: set[str]):
    return value if isinstance(value, str) and value in allowed else None


def safe_time(value):
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if parsed.tzinfo is not None else None


def safe_attempts(items):
    if not isinstance(items, list) or len(items) > MAX_RECORDS:
        raise ValueError("Attempt count exceeds bound")
    if any(not isinstance(item, dict) for item in items):
        raise ValueError("Invalid attempt record")
    return [{"number": item.get("number") if type(item.get("number")) is int else None,
             "status": limited(item.get("status"), STATUSES),
             "error_code": limited(item.get("error_code"), ERROR_CODES),
             "started_at": safe_time(item.get("started_at")),
             "finished_at": safe_time(item.get("finished_at"))} for item in items]


def safe_events(items):
    if not isinstance(items, list) or len(items) > MAX_RECORDS:
        raise ValueError("Event count exceeds bound")
    if any(not isinstance(item, dict) for item in items):
        raise ValueError("Invalid event record")
    allowed = {"submitted", "dispatched", "running", "succeeded", "failed",
               "deadline_exceeded", "retry_requested", "cancelled", "worker_killed",
               "worker_restarted", "explicit_retry_requested", "job_status"}
    return [{"event": limited(item.get("event"), allowed),
             "generation": item.get("generation") if type(item.get("generation")) is int else None,
             "timestamp": safe_time(item.get("timestamp") or item.get("at"))} for item in items]


def safe_timings(value):
    if not isinstance(value, dict):
        return {}
    return {key: number for key, number in value.items() if key in TIMING_KEYS
            and type(number) in (int, float) and 0 <= number < 100_000}


def safe_lineage(value):
    if not isinstance(value, dict):
        return {}
    return {key: item for key in ("code_hash", "inference_config_hash", "prompt_hash", "taxonomy_hash")
            if isinstance(item := value.get(key), str) and len(item) == 64
            and all(c in "0123456789abcdef" for c in item.lower())}


def metrics_snapshot(raw: str) -> dict:
    allowed = {"video_job_capacity", "video_jobs_outstanding", "video_oldest_queued_job_seconds"}
    found = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in allowed and re.fullmatch(r"\d+(?:\.\d+)?", parts[1]):
            found[parts[0]] = float(parts[1])
    return found


def finish_bundle(source_kind: str, source_sha256: dict, observations: dict) -> dict:
    bundle = {"schema_version": SCHEMA, "source_kind": source_kind,
              "source_sha256": source_sha256, "observations": observations,
              "missing_evidence": ["raw_logs", "per_job_gpu_telemetry"]}
    bundle["bundle_sha256"] = digest(canonical(bundle))
    return bundle


def from_report(path: Path) -> dict:
    report, source_hash = read_json(path)
    purpose = report.get("purpose")
    if purpose == "controlled local active-worker interruption":
        timeline = report.get("timeline", [])
        events = safe_events(report.get("events", []))
        events.extend(safe_events(timeline))
        events = sorted((item for item in events if item["event"] and item["timestamp"]),
                        key=lambda item: item["timestamp"])
        if len(events) > MAX_RECORDS:
            raise ValueError("Combined event count exceeds bound")
        observations = {"status": limited(report.get("final_status"), STATUSES),
                        "attempts": safe_attempts(report.get("attempts", [])),
                        "events": events, "admission": None,
                        "timings_seconds": {},
                        "input_sha256": report.get("input_sha256") if isinstance(report.get("input_sha256"), str)
                        and re.fullmatch(r"[0-9a-f]{64}", report["input_sha256"]) else None,
                        "model_revision": report.get("result_model_revision") if
                        isinstance(report.get("result_model_revision"), str) and
                        len(report["result_model_revision"]) == 40 and
                        all(c in "0123456789abcdef" for c in report["result_model_revision"].lower()) else None}
        kind = "recovery_report"
    elif purpose == "local GPU admission demonstration":
        submissions = report.get("submissions", [])
        if not isinstance(submissions, list) or len(submissions) > MAX_RECORDS or any(
                not isinstance(item, dict) for item in submissions):
            raise ValueError("Submission count exceeds bound")
        observations = {"status": None, "attempts": [], "events": [],
                        "admission": {"capacity": report.get("capacity") if
                                      type(report.get("capacity")) is int else None,
                                      "http_statuses": [entry.get("http_status") if
                                      entry.get("http_status") in (202, 429) else None
                                      for entry in submissions],
                                      "after_drain_status": (report.get("after_drain") or {}).get("http_status")},
                        "timings_seconds": {}, "model_revision": None}
        observations["input_sha256"] = report.get("input_sha256") if isinstance(
            report.get("input_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", report["input_sha256"]) else None
        kind = "admission_report"
    else:
        raise ValueError("Unsupported evidence report purpose")
    return finish_bundle(kind, {"report": source_hash}, observations)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("Redirects are not allowed for evidence collection")


def from_api(base_url: str, job_id: str, api_key: str = "") -> dict:
    parsed = urlparse(base_url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or parsed.username or parsed.password):
        raise ValueError("Evidence collection accepts only a loopback HTTP API")
    try:
        job_id = str(UUID(job_id))
    except ValueError:
        raise ValueError("Expected a job UUID")
    opener = build_opener(ProxyHandler({}), NoRedirect)
    source_hashes = {}

    def fetch(label, route, json_response=True):
        req = Request(base_url.rstrip("/") + route,
                      headers={"X-API-Key": api_key} if api_key else {})
        with opener.open(req, timeout=10) as response:
            raw = response.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError("API evidence exceeds 2 MB")
        source_hashes[label] = digest(raw)
        return json.loads(raw) if json_response else raw.decode("utf-8")

    prefix = "/api/v1/jobs/" + job_id
    job = fetch("job", prefix)
    attempts = fetch("attempts", prefix + "/attempts")
    events = fetch("events", prefix + "/events")
    live = fetch("live", "/health/live")
    metrics = fetch("metrics", "/metrics", False)
    result = job.get("result") or {}
    revision = result.get("model_revision")
    release_id = live.get("release_id")
    observations = {"status": limited(job.get("status"), STATUSES),
                    "attempts": safe_attempts(attempts), "events": safe_events(events),
                    "admission": None, "timings_seconds": safe_timings(result.get("timings")),
                    "input_sha256": result.get("input_sha256") if isinstance(result.get("input_sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", result["input_sha256"]) else None,
                    "model_revision": revision if isinstance(revision, str) and len(revision) in (40, 64)
                    and all(c in "0123456789abcdef" for c in revision.lower()) else None,
                    "deployment_id": limited(job.get("deployment_id"), {"video-summary-v1", "text-topic-v1"}),
                    "lineage_hashes": safe_lineage(result.get("lineage")),
                    "current_snapshot": {"observed_at": datetime.now(timezone.utc).isoformat(),
                                         "release_id_sha256": digest(release_id.encode()) if
                                         isinstance(release_id, str) and len(release_id) <= 64 else None,
                                         "metrics": metrics_snapshot(metrics)}}
    # Current state is deliberately distinct from the old job's producer identity.
    bundle = finish_bundle("live_api", source_hashes, observations)
    bundle["missing_evidence"].extend(["producer_release_id", "external_worker_lifecycle_events"])
    bundle["bundle_sha256"] = digest(canonical({k: v for k, v in bundle.items() if k != "bundle_sha256"}))
    return bundle


def validate_bundle(bundle: dict):
    if set(bundle) != {"schema_version", "source_kind", "source_sha256", "observations",
                       "missing_evidence", "bundle_sha256"}:
        raise ValueError("Unknown bundle fields")
    if bundle.get("schema_version") != SCHEMA:
        raise ValueError("Unknown bundle schema")
    if bundle.get("source_kind") not in {"recovery_report", "admission_report", "live_api", "synthetic_variant"}:
        raise ValueError("Unknown source kind")
    sources = bundle.get("source_sha256")
    if not isinstance(sources, dict) or not 1 <= len(sources) <= 6 or any(
            key not in {"report", "job", "attempts", "events", "live", "metrics", "parent_bundle"}
            or not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
            for key, value in sources.items()):
        raise ValueError("Invalid source digests")
    missing = bundle.get("missing_evidence")
    if not isinstance(missing, list) or len(missing) > 10 or any(
            item not in {"raw_logs", "per_job_gpu_telemetry", "producer_release_id",
                         "external_worker_lifecycle_events"} for item in missing):
        raise ValueError("Invalid missing-evidence markers")
    observed = bundle.get("observations")
    if not isinstance(observed, dict) or set(observed) - {"status", "attempts", "events", "admission",
                                                "timings_seconds", "model_revision", "input_sha256", "deployment_id",
                                                "lineage_hashes", "current_snapshot"}:
        raise ValueError("Invalid observations")
    if (observed.get("status") is not None and observed["status"] not in STATUSES
            or observed.get("attempts") != safe_attempts(observed.get("attempts"))
            or observed.get("events") != safe_events(observed.get("events"))
            or observed.get("timings_seconds") != safe_timings(observed.get("timings_seconds"))):
        raise ValueError("Unredacted or invalid operational fields")
    revision = observed.get("model_revision")
    if revision is not None and (not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision)):
        raise ValueError("Invalid model revision")
    input_hash = observed.get("input_sha256")
    if input_hash is not None and (not isinstance(input_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", input_hash)):
        raise ValueError("Invalid input hash")
    if "lineage_hashes" in observed and observed["lineage_hashes"] != safe_lineage(observed["lineage_hashes"]):
        raise ValueError("Invalid lineage hashes")
    admission = observed.get("admission")
    if admission is not None and (not isinstance(admission, dict) or set(admission) != {
            "capacity", "http_statuses", "after_drain_status"} or
            (admission["capacity"] is not None and type(admission["capacity"]) is not int) or
            not isinstance(admission["http_statuses"], list) or
            len(admission["http_statuses"]) > MAX_RECORDS or
            any(item not in (202, 429, None) for item in admission["http_statuses"]) or
            admission["after_drain_status"] not in (202, 429, None)):
        raise ValueError("Invalid admission fields")
    if "current_snapshot" in observed:
        snapshot = observed["current_snapshot"]
        if (not isinstance(snapshot, dict) or set(snapshot) != {"observed_at", "release_id_sha256", "metrics"}
                or safe_time(snapshot["observed_at"]) != snapshot["observed_at"]
                or snapshot["release_id_sha256"] is not None and not re.fullmatch(
                    r"[0-9a-f]{64}", snapshot["release_id_sha256"]) or
                not isinstance(snapshot["metrics"], dict) or
                snapshot["metrics"] != metrics_snapshot("\n".join(
                    f"{key} {value}" for key, value in snapshot["metrics"].items()))):
            raise ValueError("Invalid current snapshot")
    recorded = bundle.get("bundle_sha256")
    unsigned = {k: v for k, v in bundle.items() if k != "bundle_sha256"}
    if recorded != digest(canonical(unsigned)):
        raise ValueError("Bundle integrity mismatch")


def diagnose(bundle: dict) -> dict:
    validate_bundle(bundle)
    observed = bundle["observations"]
    events = observed.get("events") or []
    attempts = observed.get("attempts") or []
    citations = []
    kill = next((i for i, item in enumerate(events) if item.get("event") == "worker_killed"), None)
    timeout = next((i for i, item in enumerate(attempts) if item.get("error_code") == "timeout"), None)
    ordered = False
    if kill is not None and timeout is not None:
        killed_at = safe_time(events[kill].get("timestamp"))
        finished_at = safe_time(attempts[timeout].get("finished_at"))
        if killed_at and finished_at:
            ordered = datetime.fromisoformat(killed_at.replace("Z", "+00:00")) < datetime.fromisoformat(
                finished_at.replace("Z", "+00:00"))
    if ordered:
        cause = "worker_interruption"
        citations = [f"observations.events[{kill}].event", f"observations.attempts[{timeout}].error_code"]
    else:
        admission = observed.get("admission") or {}
        statuses = admission.get("http_statuses") or []
        capacity = admission.get("capacity")
        if type(capacity) is int and capacity > 0 and statuses.count(202) >= capacity and 429 in statuses:
            cause = "gpu_admission_limit"
            citations = ["observations.admission.capacity", "observations.admission.http_statuses"]
        elif observed.get("status") == "FAILED" and any(
                attempt.get("status") == "FAILED" and attempt.get("error_code") == "missing_input"
                for attempt in attempts):
            cause = "reported_missing_input"
            index = next(i for i, attempt in enumerate(attempts)
                         if attempt.get("status") == "FAILED" and attempt.get("error_code") == "missing_input")
            citations = ["observations.status", f"observations.attempts[{index}].error_code"]
        else:
            cause = "insufficient_evidence"
    return {"diagnosis": cause, "citations": citations,
            "reason": {"worker_interruption": "Worker kill and timed-out attempt are both recorded.",
                       "gpu_admission_limit": "Accepted jobs reached the recorded capacity and another request received 429.",
                       "reported_missing_input": "A failed attempt records the service's missing_input error code; artifact deletion or its origin is not established.",
                       "insufficient_evidence": "Available evidence does not distinguish a supported cause."}[cause]}


def compare(baseline: dict, candidate: dict) -> dict:
    """Compare two jobs from the same deployment without inferring causality."""
    validate_bundle(baseline)
    validate_bundle(candidate)
    before = baseline["observations"]
    after = candidate["observations"]
    deployment = before.get("deployment_id")
    if not deployment or deployment != after.get("deployment_id"):
        return {"comparable": False, "reason": "Both bundles need the same known deployment ID."}
    input_hash = before.get("input_sha256")
    if not input_hash or input_hash != after.get("input_sha256"):
        return {"comparable": False, "reason": "Both bundles need the same known input hash."}
    shared = set(before.get("timings_seconds", {})) & set(after.get("timings_seconds", {}))
    stages = {}
    for name in sorted(shared):
        old, new = before["timings_seconds"][name], after["timings_seconds"][name]
        stages[name] = {"baseline_seconds": old, "candidate_seconds": new,
                        "delta_seconds": new - old, "ratio": new / old if old else None,
                        "citations": [f"baseline.observations.timings_seconds.{name}",
                                      f"candidate.observations.timings_seconds.{name}"]}
    return {"comparable": True, "deployment_id": deployment,
            "input_sha256": input_hash,
            "model_revision_equal": before.get("model_revision") == after.get("model_revision") if
            before.get("model_revision") and after.get("model_revision") else None,
            "lineage_hashes_equal": before.get("lineage_hashes") == after.get("lineage_hashes") if
            before.get("lineage_hashes") and after.get("lineage_hashes") else None,
            "statuses": [before.get("status"), after.get("status")],
            "stage_differences": stages,
            "interpretation_limit": "Timing differences alone do not identify a cause; GPU and host conditions may differ."}
