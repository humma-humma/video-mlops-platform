"""Build a small, explicitly report-derived diagnostic pilot corpus."""

import argparse
from copy import deepcopy
from pathlib import Path

from scripts.diagnostic_workbench import write_json
from src.diagnostics import finish_bundle, from_report


ROOT = Path(__file__).resolve().parents[1]


def variant(parent: dict, observations: dict) -> dict:
    return finish_bundle("synthetic_variant", {"parent_bundle": parent["bundle_sha256"]}, observations)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/diagnostics/pilot"))
    args = parser.parse_args(argv)
    output = args.output_dir
    recovery = from_report(ROOT / "reports/recovery_demo.json")
    admission = from_report(ROOT / "reports/admission_demo.json")
    cases = []

    def add(case_id, bundle, expected, split, origin):
        name = case_id + ".json"
        write_json(output / name, bundle)
        cases.append({"id": case_id, "bundle": name, "expected": expected,
                      "split": split, "origin": origin})

    add("recorded_worker_interruption", recovery, "worker_interruption", "development", "recorded")
    add("recorded_gpu_admission", admission, "gpu_admission_limit", "development", "recorded")

    no_kill = deepcopy(recovery["observations"])
    no_kill["events"] = [event for event in no_kill["events"] if event["event"] != "worker_killed"]
    add("timeout_without_kill", variant(recovery, no_kill), "insufficient_evidence",
        "held_out", "synthetic_missing_evidence")

    no_timeout = deepcopy(recovery["observations"])
    for attempt in no_timeout["attempts"]:
        if attempt["error_code"] == "timeout":
            attempt["error_code"] = None
    add("kill_without_timeout", variant(recovery, no_timeout), "insufficient_evidence",
        "held_out", "synthetic_missing_evidence")

    late_kill = deepcopy(recovery["observations"])
    for event in late_kill["events"]:
        if event["event"] == "worker_killed":
            event["timestamp"] = "2026-10-17T08:54:00+00:00"
    add("kill_after_timeout", variant(recovery, late_kill), "insufficient_evidence",
        "held_out", "synthetic_temporal_confounder")

    underfilled = deepcopy(admission["observations"])
    underfilled["admission"]["capacity"] = 3
    add("rejection_below_capacity", variant(admission, underfilled), "insufficient_evidence",
        "held_out", "synthetic_confounded_rejection")

    no_capacity = deepcopy(admission["observations"])
    no_capacity["admission"]["capacity"] = None
    add("rejection_without_capacity", variant(admission, no_capacity), "insufficient_evidence",
        "held_out", "synthetic_missing_evidence")

    without_drain = deepcopy(admission["observations"])
    without_drain["admission"]["after_drain_status"] = None
    add("admission_without_drain_probe", variant(admission, without_drain), "gpu_admission_limit",
        "held_out", "synthetic_missing_evidence")

    write_json(output / "cases.json", {"schema_version": "diagnostic-cases-v1", "cases": cases,
                                     "limits": "Variants derive from two recorded local incidents; held-out means withheld from the simple rules, not an independent incident population."})
    print(f"Built {len(cases)} labeled cases in {output}")


if __name__ == "__main__":
    main()
