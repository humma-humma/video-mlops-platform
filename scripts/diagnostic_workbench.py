"""Export bounded incident evidence and score an offline deterministic diagnosis."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from src.diagnostics import compare, diagnose, from_api, from_report, read_json, validate_bundle


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
            if (case.get("expected") not in {"worker_interruption", "gpu_admission_limit", "insufficient_evidence"}
                    or case.get("split") not in {"development", "held_out"}):
                raise ValueError("Invalid case label or split")
            case_path = (root / case["bundle"]).resolve()
            if not case_path.is_relative_to(root):
                raise ValueError("Case bundle must stay inside the case directory")
            bundle = read_bundle(case_path)
            if bundle["bundle_sha256"] in seen_hashes:
                raise ValueError("Duplicate bundle in evaluation")
            seen_hashes.add(bundle["bundle_sha256"])
            predicted = diagnose(bundle)
            citations_valid = all(resolve_path(bundle, path) is not None
                                  for path in predicted["citations"])
            rows.append({"case_id": case["id"], "split": case["split"],
                         "origin": case["origin"], "expected": case["expected"],
                         "predicted": predicted["diagnosis"],
                         "bundle_sha256": bundle["bundle_sha256"],
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
                  "false_confident": sum(row["expected"] == "insufficient_evidence" and
                                         row["predicted"] != "insufficient_evidence" for row in rows),
                  "cited_cases": sum(row["predicted"] != "insufficient_evidence" for row in rows),
                  "citations_valid": all(row["citations_valid"] for row in rows),
                  "scope": "Small pilot with report-derived variants; not independent generalization evidence"}
        write_json(args.output, output)
        print(f"{output['correct']}/{output['total']} diagnoses matched labels; "
              f"citations valid: {output['citations_valid']}")


def resolve_path(value, path):
    import re
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
