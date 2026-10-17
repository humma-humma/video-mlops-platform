"""Compare reports against an explicitly reviewed, immutable baseline policy."""
import argparse
import json
from pathlib import Path

from src.experiments import GatePolicy, evaluate_gate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    gate = evaluate_gate(read(args.candidate), read(args.baseline), GatePolicy.model_validate(read(args.policy)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print("PASS candidate gate" if gate["passed"] else "FAIL candidate gate: " + "; ".join(gate["reasons"]))
    raise SystemExit(0 if gate["passed"] else 1)


if __name__ == "__main__":
    main()
