"""The exporter must preserve operational evidence without copying user content."""

from copy import deepcopy
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.diagnostics import (compare, diagnose, digest, finish_bundle, from_api, from_report,
                             safe_attempts, validate_bundle)


ROOT = Path(__file__).resolve().parents[1]


def test_recorded_cases_and_integrity():
    recovery = from_report(ROOT / "reports/recovery_demo.json")
    admission = from_report(ROOT / "reports/admission_demo.json")
    assert diagnose(recovery)["diagnosis"] == "worker_interruption"
    assert diagnose(admission)["diagnosis"] == "gpu_admission_limit"
    assert all(diagnose(bundle)["citations"] for bundle in (recovery, admission))
    assert "bd4908b7" not in json.dumps(recovery)
    assert "56fe9a77" not in json.dumps(admission)
    assert "Worker deadline exceeded" not in json.dumps(recovery)
    damaged = deepcopy(recovery)
    damaged["observations"]["attempts"][0]["error_code"] = None
    with pytest.raises(ValueError, match="integrity"):
        validate_bundle(damaged)
    leaked = deepcopy(recovery["observations"])
    leaked["summary"] = "private generated text"
    with pytest.raises(ValueError, match="observations"):
        validate_bundle(finish_bundle("synthetic_variant", {"parent_bundle": recovery["bundle_sha256"]}, leaked))


def test_missing_evidence_abstains():
    recovery = from_report(ROOT / "reports/recovery_demo.json")
    observations = deepcopy(recovery["observations"])
    observations["events"] = [event for event in observations["events"]
                              if event["event"] != "worker_killed"]
    assert diagnose(finish_bundle("synthetic_variant", {"parent_bundle": recovery["bundle_sha256"]},
                                  observations))["diagnosis"] == "insufficient_evidence"
    late = deepcopy(recovery["observations"])
    for event in late["events"]:
        if event["event"] == "worker_killed":
            event["timestamp"] = "2026-10-17T08:54:00+00:00"
    assert diagnose(finish_bundle("synthetic_variant", {"parent_bundle": recovery["bundle_sha256"]},
                                  late))["diagnosis"] == "insufficient_evidence"
    admission = from_report(ROOT / "reports/admission_demo.json")
    observations = deepcopy(admission["observations"])
    observations["admission"]["capacity"] = 3
    assert diagnose(finish_bundle("synthetic_variant", {"parent_bundle": admission["bundle_sha256"]},
                                  observations))["diagnosis"] == "insufficient_evidence"


def test_reported_missing_input_requires_failed_attempt_and_generic_failure_abstains():
    attempts = safe_attempts([{"number": 1, "status": "FAILED", "error_code": "missing_input"},
                              {"number": 2, "status": "FAILED", "error_code": "internal"}])
    assert [attempt["error_code"] for attempt in attempts] == ["missing_input", "internal"]
    observations = {"status": "FAILED", "attempts": attempts, "events": [],
                    "admission": None, "timings_seconds": {}}
    bundle = finish_bundle("synthetic_variant", {"parent_bundle": "a" * 64}, observations)
    result = diagnose(bundle)
    assert result["diagnosis"] == "reported_missing_input"
    assert result["citations"] == ["observations.status", "observations.attempts[0].error_code"]
    observations["attempts"] = attempts[1:]
    assert diagnose(finish_bundle("synthetic_variant", {"parent_bundle": "a" * 64},
                                  observations))["diagnosis"] == "insufficient_evidence"


def test_api_export_is_loopback_read_only_bounded_and_redacted():
    job_id = "48168988-af5a-4f1d-97eb-16f8cccc5ffd"
    prefix = "/api/v1/jobs/" + job_id
    responses = {
        prefix: {"status": "SUCCEEDED", "deployment_id": "text-topic-v1",
                 "result": {"summary": "SECRET user content", "output": {"text": "SECRET"},
                            "timings": {"total": 1.5}, "model_revision": "a" * 64,
                            "input_sha256": "b" * 64,
                            "lineage": {"code_hash": "d" * 64, "secret": "SECRET config"}}},
        prefix + "/attempts": [{"number": 1, "status": "SUCCEEDED", "error_code": None,
                                  "error": "SECRET error", "started_at": "2026-10-17T10:00:00Z"}],
        prefix + "/events": [{"event": "succeeded", "generation": 0,
                                "trace_id": "SECRET trace", "timestamp": "2026-10-17T10:00:01Z"}],
        "/health/live": {"status": "ok", "release_id": "test-release"},
        "/metrics": "video_job_capacity 2\nvideo_jobs_outstanding 1\nSECRET metric payload\n",
    }
    calls = []

    class FakeResponse:
        def __init__(self, value):
            self.stream = io.BytesIO((value if isinstance(value, str) else json.dumps(value)).encode())

        def __enter__(self):
            return self

        def __exit__(self, *unused):
            pass

        def read(self, count):
            return self.stream.read(count)

    class FakeOpener:
        def open(self, request, timeout):
            calls.append((request.get_method(), request.full_url, timeout))
            return FakeResponse(responses[request.full_url.removeprefix("http://127.0.0.1:8000")])

    with patch("src.diagnostics.build_opener", return_value=FakeOpener()):
        bundle = from_api("http://127.0.0.1:8000", job_id, "SECRET key")
    serialized = json.dumps(bundle)
    assert "SECRET" not in serialized and job_id not in serialized
    assert bundle["observations"]["timings_seconds"] == {"total": 1.5}
    assert bundle["observations"]["model_revision"] == "a" * 64
    assert bundle["observations"]["lineage_hashes"] == {"code_hash": "d" * 64}
    assert bundle["observations"]["current_snapshot"]["metrics"]["video_jobs_outstanding"] == 1
    assert len(calls) == 5 and all(method == "GET" and timeout == 10 for method, _, timeout in calls)
    assert digest(b"test-release") == bundle["observations"]["current_snapshot"]["release_id_sha256"]
    with pytest.raises(ValueError, match="loopback"):
        from_api("https://example.com", job_id)

    later = deepcopy(bundle["observations"])
    later["timings_seconds"]["total"] = 3.0
    candidate = finish_bundle("synthetic_variant", {"parent_bundle": bundle["bundle_sha256"]}, later)
    difference = compare(bundle, candidate)
    assert difference["comparable"] is True
    assert difference["stage_differences"]["total"]["ratio"] == 2.0
    later["deployment_id"] = "video-summary-v1"
    other_deployment = finish_bundle("synthetic_variant", {"parent_bundle": bundle["bundle_sha256"]}, later)
    assert compare(bundle, other_deployment)["comparable"] is False
    later["deployment_id"] = "text-topic-v1"
    later["input_sha256"] = "c" * 64
    other_input = finish_bundle("synthetic_variant", {"parent_bundle": bundle["bundle_sha256"]}, later)
    assert compare(bundle, other_input)["comparable"] is False
