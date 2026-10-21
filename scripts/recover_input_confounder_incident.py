"""Finish a CPU-input challenge whose faults ran but evidence assertion failed."""

from datetime import datetime, timezone
import os
from pathlib import Path
import time
from urllib.request import ProxyHandler, build_opener

from scripts.diagnostic_workbench import main as workbench, write_json
from scripts.input_confounder_incident import OUTPUT, settle, submit
from scripts.result_loss_incident import request
from src.diagnostics import NoRedirect, diagnose, digest, from_api, read_json


def main():
    output = OUTPUT
    if (output / "incident.json").exists():
        raise FileExistsError("Incident evidence already exists")
    state, state_hash = read_json(output / "run_state.json")
    protocol, protocol_hash = read_json(output / "protocol.json")
    cases, cases_hash = read_json(output / "cases.json")
    if not state["cpu_worker_started"] or not all(state["object_restored_exactly"].values()):
        raise RuntimeError("The recorded restoration did not complete")
    root = Path(__file__).resolve().parents[1]
    rules_hash = digest((root / "src" / "diagnostics.py").read_bytes())
    if rules_hash != protocol["rules_sha256"]:
        raise RuntimeError("Diagnostic rules differ from the preregistered version")
    key = os.environ.get("VIDEO_API_KEY", "")
    base = "http://127.0.0.1:8000"
    opener = build_opener(ProxyHandler({}), NoRedirect)
    wanted = state["job_id_sha256"]
    jobs = {}
    for offset in range(0, 1000, 100):
        status, page = request(opener, base,
                               f"/api/v1/jobs?deployment_id=text-topic-v1&limit=100&offset={offset}", key)
        if status != 200:
            raise RuntimeError(f"Job listing returned HTTP {status}")
        for job in page:
            for name, job_hash in wanted.items():
                if digest(job["job_id"].encode()) == job_hash:
                    jobs[name] = job["job_id"]
        if len(jobs) == len(wanted) or len(page) < 100:
            break
    if set(jobs) != set(wanted):
        raise RuntimeError("Could not match both saved job hashes to local jobs")
    bundles = {}
    for case in cases["cases"]:
        name = case["id"]
        bundle = from_api(base, jobs[name], key)
        if bundle["observations"]["status"] != "FAILED":
            raise RuntimeError(f"{name} is not a failed job")
        bundles[name] = bundle
    control_id = submit(opener, base, key)
    control = settle(opener, base, key, control_id, time.monotonic() + 60)
    if control["status"] != "SUCCEEDED":
        raise RuntimeError(f"Restored-worker control ended {control['status']}")
    for case in cases["cases"]:
        write_json(output / case["bundle"], bundles[case["id"]])
    write_json(output / "control_job.json", from_api(base, control_id, key))
    observations = {}
    for name, bundle in bundles.items():
        spec = protocol["cases"][name]
        attempts = bundle["observations"]["attempts"]
        code = attempts[0]["error_code"] if len(attempts) == 1 else None
        stage = bundle["observations"].get("failure_stage")
        diagnosis = diagnose(bundle)["diagnosis"]
        observations[name] = {
            "attempt_code": code, "failure_stage": stage, "diagnosis": diagnosis,
            "attempt_code_matches_registration": code == spec["expected_attempt_code"],
            "failure_stage_matches_registration": stage == spec["expected_failure_stage"],
            "diagnosis_matches_registration": diagnosis == spec["expected_diagnosis"],
        }
    ledger = {
        "schema_version": "cpu-input-challenge-recovered-v1",
        "protocol_sha256": protocol_hash,
        "case_manifest_sha256": cases_hash,
        "rules_sha256": rules_hash,
        "recovery_note": "Original runner stopped at a preregistered attempt-code mismatch after restoring inputs; no faults were rerun.",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "job_id_sha256": wanted,
        "observations": observations,
        "control_status": control["status"],
        "limits": protocol["limits"],
    }
    write_json(output / "ledger.json", ledger)
    write_json(output / "incident.json", {
        "schema_version": "cpu-input-challenge-recovered-v1",
        "protocol_sha256": protocol_hash,
        "run_state_sha256": state_hash,
        "ledger_sha256": digest((output / "ledger.json").read_bytes()),
        "bundle_sha256": {name: bundle["bundle_sha256"] for name, bundle in bundles.items()},
    })
    workbench(["evaluate", "--cases", str(output / "cases.json"),
               "--output", str(output / "evaluation.json")])
    print("Recovered original live cases; see ledger.json for registered expectation mismatches")


if __name__ == "__main__":
    main()
