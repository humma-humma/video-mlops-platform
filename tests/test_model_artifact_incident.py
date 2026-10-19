"""The saved live incident must match its registered protocol and restoration record."""

import hashlib
import json
from pathlib import Path

from src.diagnostics import diagnose, validate_bundle


ROOT = Path(__file__).resolve().parents[1] / "reports" / "diagnostics" / "model-artifact-live"


def test_model_artifact_live_evidence_and_control():
    def read(name):
        raw = (ROOT / name).read_bytes()
        return json.loads(raw), hashlib.sha256(raw).hexdigest()

    protocol, protocol_hash = read("protocol.json")
    cases, cases_hash = read("cases.json")
    ledger, ledger_hash = read("ledger.json")
    state, state_hash = read("run_state.json")
    incident, _ = read("incident.json")
    failed, _ = read("failed_job.json")
    control, _ = read("control_job.json")
    evaluation, _ = read("evaluation.json")

    assert ledger["registered_commit"] == "1d1c69c25e29b03b7ff1947efaffd001002e5fe6"
    assert incident["protocol_sha256"] == ledger["protocol_sha256"] == protocol_hash
    assert incident["ledger_sha256"] == ledger_hash
    assert incident["run_state_sha256"] == state_hash
    assert incident["failure_bundle_sha256"] == failed["bundle_sha256"]
    assert incident["control_bundle_sha256"] == control["bundle_sha256"]
    assert evaluation["case_manifest_sha256"] == cases_hash
    assert evaluation["cases"][0]["bundle_sha256"] == failed["bundle_sha256"]
    assert ledger["model_artifact_sha256"] == state["model_artifact_sha256"]
    assert state["artifact_restored_exactly"] is True
    assert ledger["control_status"] == control["observations"]["status"] == "SUCCEEDED"
    assert control["observations"]["model_revision"] == state["model_artifact_sha256"]
    assert failed["observations"]["status"] == "FAILED"
    assert failed["observations"]["attempts"][0]["error_code"] == (
        protocol["expected_observations_after_repair"]["attempt_error_code"])
    validate_bundle(failed)
    validate_bundle(control)
    assert diagnose(failed)["diagnosis"] == cases["cases"][0]["expected"]
    assert evaluation["correct_diagnoses"] == evaluation["total"] == 1
    assert evaluation["citations_valid"] is True
    assert evaluation["false_confident"] == 0
