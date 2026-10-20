"""Fail an image build when its packaged CPU model is missing or mismatched."""

import argparse
import hashlib
import json
from pathlib import Path


def verify(path: Path, expected_sha256: str) -> str:
    payload = path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected_sha256:
        raise ValueError("Packaged model SHA-256 differs from the reviewed artifact")
    model = json.loads(payload)
    if model.get("schema_version") != 1 or not model.get("labels"):
        raise ValueError("Packaged model schema is invalid")
    return actual


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args(argv)
    if len(args.sha256) != 64 or any(c not in "0123456789abcdef" for c in args.sha256):
        parser.error("Expected a lowercase SHA-256 digest")
    print("PASS packaged model artifact", verify(args.artifact, args.sha256))


if __name__ == "__main__":
    main()
