"""Log a reproducible candidate comparison and optionally register a passed bundle."""
import argparse
import json
from pathlib import Path

from src.experiments import GatePolicy
from src.tracking import track_candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--tracking-uri", default="http://localhost:5000")
    parser.add_argument("--register-as")
    parser.add_argument("--image-digest")
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = track_candidate(read(args.candidate), read(args.baseline), GatePolicy.model_validate(read(args.policy)),
        tracking_uri=args.tracking_uri, registry_name=args.register_as, image_digest=args.image_digest)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
