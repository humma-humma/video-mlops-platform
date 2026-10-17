"""Verify the exact input bytes referenced by a dataset manifest."""
import argparse
import json
from pathlib import Path

from src.lineage import sha256_file, verify_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/tiktok-video-v1.json"))
    parser.add_argument("--dataset-root", type=Path, default=Path("data/inputs"))
    args = parser.parse_args()
    errors = verify_manifest(json.loads(args.manifest.read_text(encoding="utf-8")), args.dataset_root)
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print(f"PASS manifest integrity: {sha256_file(args.manifest)}")


if __name__ == "__main__":
    main()
