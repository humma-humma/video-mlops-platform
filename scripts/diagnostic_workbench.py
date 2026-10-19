"""Export bounded incident evidence and score an offline deterministic diagnosis."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from src.diagnostics import compare, diagnose, diagnose_pair, from_api, from_report, read_json, validate_bundle


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def read_bundle(path: Path):
    value, _ = read_json(path)
    validate_bundle(value)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("export-report", help="Use a recorded recovery/admission report")
    report.add_argument("--source", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    job = sub.add_parser("export-job", help="Collect one job from the loopback API, read-only")
    job.add_argument("--job-id", required=True)
    job.add_argument("--base-url", default="http://127.0.0.1:8000")
    job.add_argument("--output", type=Path, required=True)
    analysis = sub.add_parser("analyze", help="Analyze an offline bundle")
    analysis.add_argument("--bundle", type=Path, required=True)
    analysis.add_argument("--output", type=Path)
    pair_analysis = sub.add_parser("analyze-pair", help="Identify a measured regression between two offline bundles")
    pair_analysis.add_argument("--baseline", type=Path, required=True)
    pair_analysis.add_argument("--candidate", type=Path, required=True)
    pair_analysis.add_argument("--output", type=Path)
    comparison = sub.add_parser("compare", help="Compare two offline job bundles")
    comparison.add_argument("--baseline", type=Path, required=True)
    comparison.add_argument("--candidate", type=Path, required=True)
    comparison.add_argument("--output", type=Path)
    evaluation = sub.add_parser("evaluate", help="Score a labeled offline case manifest")
    evaluation.add_argument("--cases", type=Path, required=True)
    evaluation.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "export-report":
        bundle = from_report(args.source)
        write_json(args.output, bundle)
        print(f"Exported {bundle['source_kind']} bundle: {args.output}")
    elif args.command == "export-job":
        bundle = from_api(args.base_url, args.job_id, os.environ.get("VIDEO_API_KEY", ""))
        write_json(args.output, bundle)
        print(f"Exported read-only job bundle: {args.output}")
    elif args.command == "analyze":
        result = diagnose(read_bundle(args.bundle))
        if args.output:
            write_json(args.output, result)
        print(json.dumps(result, indent=2))
    elif args.command == "analyze-pair":
        result = diagnose_pair(read_bundle(args.baseline), read_bundle(args.candidate))
        if args.output:
            write_json(args.output, result)
        print(json.dumps(result, indent=2))
    elif args.command == "compare":
        result = compare(read_bundle(args.baseline), read_bundle(args.candidate))
        if args.output:
            write_json(args.output, result)
        print(json.dumps(result, indent=2))
    else:
        manifest, manifest_hash = read_json(args.cases)
        cases = manifest.get("cases")
        if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
            raise ValueError("Case count must be 1..100")
        root = args.cases.parent.resolve()
        rows = []
        seen_hashes = set()
        for case in cases:
            if (case.get("expected") not in {"worker_interruption", "gpu_admission_limit",
                    "reported_missing_input", "reported_artifact_check_failure",
                    "reported_model_artifact_unavailable",
                    "reported_decode_failure",
                    "reported_artifact_download_failure",
                    "reported_result_write_failure", "preparation_latency_regression",
                    "artifact_download_latency_regression", "insufficient_evidence"}
                    or case.get("split") not in {"development", "held_out"}):
                raise ValueError("Invalid case label or split")
            case_path = (root / case["bundle"]).resolve()
            if not case_path.is_relative_to(root):
                raise ValueError("Case bundle must stay inside the case directory")
            bundle = read_bundle(case_path)
            if bundle["bundle_sha256"] in seen_hashes:
                raise ValueError("Duplicate bundle in evaluation")
            seen_hashes.add(bundle["bundle_sha256"])
            baseline = None
            if "baseline" in case:
                baseline_path = (root / case["baseline"]).resolve()
                if not baseline_path.is_relative_to(root):
                    raise ValueError("Baseline bundle must stay inside the case directory")
                baseline = read_bundle(baseline_path)
            predicted = diagnose_pair(baseline, bundle) if baseline else diagnose(bundle)
            citation_root = {"baseline": baseline, "candidate": bundle} if baseline else bundle
            citations_valid = all(resolve_path(citation_root, path) is not None
                                  for path in predicted["citations"])
            rows.append({"case_id": case["id"], "split": case["split"],
                         "origin": case["origin"], "expected": case["expected"],
                         "predicted": predicted["diagnosis"],
                         "bundle_sha256": bundle["bundle_sha256"],
                         "baseline_bundle_sha256": baseline["bundle_sha256"] if baseline else None,
                         "correct": predicted["diagnosis"] == case["expected"],
                         "citations_valid": citations_valid})
        output = {"schema_version": "diagnostic-evaluation-v1", "cases": rows,
                  "case_manifest_sha256": manifest_hash,
                  "rules_sha256": hashlib.sha256((Path(__file__).resolve().parents[1] /
                                  "src/diagnostics.py").read_bytes()).hexdigest(),
                  "correct": sum(row["correct"] for row in rows), "total": len(rows),
                  "by_split": {split: {"correct": sum(row["correct"] for row in rows if row["split"] == split),
                                       "total": sum(row["split"] == split for row in rows)}
                               for split in ("development", "held_out")},
                  "abstentions": sum(row["predicted"] == "insufficient_evidence" for row in rows),
                  "correct_abstentions": sum(row["expected"] == "insufficient_evidence" and
                                             row["predicted"] == "insufficient_evidence" for row in rows),
                  "supported_diagnoses": sum(row["expected"] != "insufficient_evidence" for row in rows),
                  "correct_diagnoses": sum(row["expected"] != "insufficient_evidence" and
                                           row["correct"] for row in rows),
                  "missed_diagnoses": sum(row["expected"] != "insufficient_evidence" and
                                          row["predicted"] == "insufficient_evidence" for row in rows),
                  "false_confident": sum(row["expected"] == "insufficient_evidence" and
                                         row["predicted"] != "insufficient_evidence" for row in rows),
                  "cited_cases": sum(row["predicted"] != "insufficient_evidence" for row in rows),
                  "citations_valid": all(row["citations_valid"] for row in rows),
                  "scope": ("Isolated service-task replay with simulated adapter and injected faults; not GPU or production evidence"
                            if all(row["origin"] == "isolated_replay" for row in rows)
                            else "Isolated API middleware replay; no deployed service or GPU-capacity observation"
                            if all(row["origin"] == "isolated_http_middleware" for row in rows)
                            else "Controlled local live cases; labels check evidence-level classification, not generalization"
                            if all(row["origin"] in {"controlled_live_api", "controlled_live_service"}
                                   for row in rows)
                            else "Historical live jobs from one local service; insufficient incident diversity for generalization"
                            if all(row["origin"] == "live_api" for row in rows)
                            else "Mixed retrospective or report-derived cases; not independent generalization evidence")}
        write_json(args.output, output)
        print(f"{output['correct']}/{output['total']} diagnoses matched labels; "
              f"citations valid: {output['citations_valid']}")


def resolve_path(value, path):
    import re
    if not re.fullmatch(r"[a-z_]+(?:\[\d+\])?(?:\.[a-z_]+(?:\[\d+\])?)*", path):
        return None
    current = value
    for field, index in re.findall(r"([a-z_]+)(?:\[(\d+)\])?", path):
        if not isinstance(current, dict) or field not in current:
            return None
        current = current[field]
        if index:
            if not isinstance(current, list) or int(index) >= len(current):
                return None
            current = current[int(index)]
    return current


if __name__ == "__main__":
    main()
