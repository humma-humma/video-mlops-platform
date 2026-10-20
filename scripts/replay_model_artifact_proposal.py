"""Replay the proposed packaged-model build gate without changing an image."""

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

from scripts.diagnostic_workbench import write_json


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "src" / "service" / "model_artifacts" / "text_topic_v1.json"
REPORT = ROOT / "reports" / "diagnostics" / "proposals" / "model_artifact_replay.json"


def probe(path, expected):
    run = subprocess.run([sys.executable, "-m", "scripts.verify_text_model_artifact",
                          "--artifact", str(path), "--sha256", expected],
                         cwd=ROOT, capture_output=True, text=True, timeout=15)
    return {"accepted": run.returncode == 0, "exit_code": run.returncode}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args(argv)
    reviewed = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    missing = MODEL.with_name("absent-replay-model.json")
    if missing.exists():
        raise RuntimeError("The reserved missing-artifact path exists")
    healthy = probe(MODEL, reviewed)
    absent = probe(missing, reviewed)
    if not healthy["accepted"] or absent["accepted"]:
        raise RuntimeError("Proposed artifact gate did not separate healthy and missing files")
    report = {
        "schema_version": "diagnostic-proposal-replay-v1",
        "reviewed_model_sha256": reviewed,
        "scenarios": {
            "healthy_artifact": {"candidate_gate": healthy},
            "missing_artifact": {"candidate_gate": absent},
        },
        "baseline": "Current Dockerfile has no packaged-model build check; baseline acceptance is inferred from its steps, not measured by this replay",
        "candidate": "Proposed verifier command executed in a local subprocess, not in a Docker image build",
        "limits": "This demonstrates the proposed preflight command only; actual candidate image builds and rollout are untested",
    }
    write_json(args.output, report)
    print("PASS proposed model artifact gate: healthy accepted, missing rejected")
    print(f"Evidence: {args.output}")


if __name__ == "__main__":
    main()
