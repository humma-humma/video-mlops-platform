"""The live incident collector must correlate logs without exporting identifiers."""

import json

import pytest

from scripts.minio_incident_demo import matching_failure_log
from src.diagnostics import digest


def test_matching_failure_log_requires_one_correlated_storage_event():
    job_id = "11111111-1111-1111-1111-111111111111"
    other = "22222222-2222-2222-2222-222222222222"
    event = json.dumps({"event": "worker_failure", "job_id": job_id,
                        "stage": "artifact_check", "error_code": "dependency",
                        "trace_id": "private-trace"})
    logs = "cpu-worker | " + json.dumps({"event": "worker_failure", "job_id": other,
                                             "stage": "inference", "error_code": "internal"})
    logs += "\ncpu-worker | " + event
    stage, source_hash = matching_failure_log(logs, job_id)
    assert stage == "artifact_check"
    assert source_hash == digest(event.encode())
    with pytest.raises(RuntimeError, match="exactly one"):
        matching_failure_log(logs + "\ncpu-worker | " + event, job_id)
    with pytest.raises(RuntimeError, match="exactly one"):
        matching_failure_log(logs, other)
