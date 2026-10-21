"""Verify the frozen CPU-input challenge and its recorded miss."""

from pathlib import Path

from src.diagnostics import diagnose, digest, read_json, validate_bundle


def main():
    root = Path(__file__).resolve().parents[1]
    directory = root / "reports" / "diagnostics" / "input-confounder-live"
    protocol, protocol_hash = read_json(directory / "protocol.json")
    cases, cases_hash = read_json(directory / "cases.json")
    state, state_hash = read_json(directory / "run_state.json")
    ledger, ledger_hash = read_json(directory / "ledger.json")
    incident, _ = read_json(directory / "incident.json")
    evaluation, _ = read_json(directory / "evaluation.json")
    rules_hash = digest((root / "src" / "diagnostics.py").read_bytes())
    assert protocol["rules_sha256"] == ledger["rules_sha256"] == evaluation["rules_sha256"] == rules_hash
    assert ledger["protocol_sha256"] == incident["protocol_sha256"] == protocol_hash
    assert ledger["case_manifest_sha256"] == evaluation["case_manifest_sha256"] == cases_hash
    assert incident["run_state_sha256"] == state_hash
    assert incident["ledger_sha256"] == ledger_hash
    assert set(state["object_restored_exactly"]) == set(protocol["cases"])
    assert all(state["object_restored_exactly"].values()) and state["cpu_worker_started"]
    assert ledger["control_status"] == "SUCCEEDED"
    control, _ = read_json(directory / "control_job.json")
    validate_bundle(control)
    assert control["observations"]["status"] == "SUCCEEDED"
    for case in cases["cases"]:
        name = case["id"]
        bundle, _ = read_json(directory / case["bundle"])
        validate_bundle(bundle)
        assert incident["bundle_sha256"][name] == bundle["bundle_sha256"]
        assert diagnose(bundle)["diagnosis"] == case["expected"] == ledger["observations"][name]["diagnosis"]
    assert evaluation["correct"] == evaluation["total"] == 2
    assert evaluation["correct_abstentions"] == 1 and evaluation["false_confident"] == 0
    assert ledger["observations"]["undecodable_text_input"]["attempt_code"] == "invalid_output"
    assert not ledger["observations"]["undecodable_text_input"]["attempt_code_matches_registration"]
    print("PASS frozen diagnoses, cited bundles, restoration, control and recorded code miss")


if __name__ == "__main__":
    main()
