"""The saved result-loss case must retain its protocol and restoration evidence."""

import hashlib
import json
from pathlib import Path

from src.diagnostics import diagnose, validate_bundle


ROOT = Path(__file__).resolve().parents[1] / "reports" / "diagnostics" / "result-loss-live"


def test_result_loss_evidence_matches_pre_registered_case():
    def read(name):
        path = ROOT / name
        return json.loads(path.read_text()), hashlib.sha256(path.read_bytes()).hexdigest()

    protocol, protocol_hash = read("protocol.json")
    manifest, _ = read("cases.json")
    ledger, ledger_hash = read("ledger.json")
    state, state_hash = read("run_state.json")
    incident, _ = read("incident.json")
    bundle, _ = read("missing_result.json")
    evaluation, _ = read("evaluation.json")

    assert ledger["registered_commit"] == incident["registered_commit"] == (
        "edbe7c3175895ccd039851fcf13a8fde04d05e63")
    assert ledger["protocol_sha256"] == incident["protocol_sha256"] == protocol_hash
    assert incident["ledger_sha256"] == bundle["source_sha256"]["report"] == ledger_hash
    assert incident["run_state_sha256"] == state_hash
    assert incident["bundle_sha256"] == bundle["bundle_sha256"]
    assert ledger["job_id_sha256"] == state["job_id_sha256"]
    assert ledger["result_object_sha256"] == state["result_object_sha256"]
    assert state["object_restored_exactly"] is True
    assert ledger["bucket_available_during_object_loss"] is True
    assert ledger["read_before"] == ledger["read_after_restore"] == 200
    assert ledger["read_during_object_loss"] == 503
    assert ledger["job_list_status_during_object_loss"] == "SUCCEEDED"
    assert bundle["observations"]["status"] == "SUCCEEDED"
    assert bundle["observations"]["result_read_http_status"] == 503
    validate_bundle(bundle)
    assert diagnose(bundle)["diagnosis"] == manifest["cases"][0]["expected"] == protocol["expected"]
    assert evaluation["correct_abstentions"] == evaluation["total"] == 1
    assert evaluation["false_confident"] == 0
