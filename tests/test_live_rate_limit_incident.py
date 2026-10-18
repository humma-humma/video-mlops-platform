"""Keep the pre-registered live rate-limit result auditable offline."""

import hashlib
import json
from pathlib import Path

from src.diagnostics import diagnose, validate_bundle


ROOT = Path(__file__).resolve().parents[1] / "reports" / "diagnostics" / "rate-limit-live"


def test_live_rate_limit_result_matches_registered_protocol():
    def read(name):
        path = ROOT / name
        return json.loads(path.read_text()), hashlib.sha256(path.read_bytes()).hexdigest()

    protocol, protocol_hash = read("protocol.json")
    manifest, _ = read("cases.json")
    ledger, ledger_hash = read("ledger.json")
    incident, _ = read("incident.json")
    bundle, _ = read("rate_limit.json")
    evaluation, _ = read("evaluation.json")

    assert ledger["registered_commit"] == incident["registered_commit"] == (
        "7c6e3720d1234404dc6638e2dbce1dbcc3118cb4")
    assert ledger["protocol_sha256"] == incident["protocol_sha256"] == protocol_hash
    assert incident["ledger_sha256"] == bundle["source_sha256"]["report"] == ledger_hash
    assert incident["bundle_sha256"] == bundle["bundle_sha256"]
    assert ledger["probe_status_counts_to_limit"]["200"] >= 1
    assert ledger["probe_status_counts_to_limit"]["429"] == 1
    assert ledger["retry_after_seconds"] == protocol["expected_observations"]["retry_after_seconds"]
    assert ledger["limited_response_kind"] == protocol["expected_observations"]["limited_response_kind"]
    assert ledger["recovered_probe_status"] == protocol["expected_observations"]["recovered_probe_status"]
    assert ledger["before"] == ledger["after"]
    assert ledger["before"]["gpu_jobs_outstanding"] == 0
    assert bundle["source_kind"] == "live_http_probe"
    validate_bundle(bundle)
    assert diagnose(bundle)["diagnosis"] == manifest["cases"][0]["expected"] == protocol["expected"]
    assert evaluation["correct_abstentions"] == evaluation["total"] == 1
    assert evaluation["false_confident"] == 0
