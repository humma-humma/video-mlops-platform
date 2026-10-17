"""Reserve stratified examples without running inference or reading their content."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from scripts.build_evaluation_subset import select_subset
from src.lineage import canonical_hash, sha256_file


def reserve_subset(manifest: dict, excluded_ids: set[str], per_category: int = 3) -> dict:
    # Validate the full manifest, including excluded records, before filtering.
    select_subset(manifest)
    remaining = {**manifest, "records": [r for r in manifest["records"]
                                         if r["video_id"] not in excluded_ids]}
    subset = select_subset(remaining, per_category, seed="video-mlops-reserved-v1")
    counts = Counter(r["category"] for r in subset["records"])
    subset.update({
        "subset_version": "reserved-eval-v1",
        "purpose": "reserved evaluation; do not tune on these examples",
        "exposure_status": "disjoint from locally recorded development/smoke/config evidence; historical exposure unknown",
        "acceptance_status": "not an acceptance set until independent annotation and historical exposure review",
        "excluded_ids": sorted(excluded_ids),
        "exclusion_hash": canonical_hash(sorted(excluded_ids)),
        "selected_category_counts": dict(sorted(counts.items())),
        "categories_below_target": {k: v for k, v in sorted(counts.items()) if v < per_category},
    })
    return subset


def collect_exposure(manifest: dict, roots: list[Path]) -> tuple[set[str], list[dict]]:
    known_ids = {r["video_id"] for r in manifest["records"]}
    excluded, sources = set(), []
    paths = {p for root in roots for p in root.rglob("*")
             if p.is_file() and p.suffix in {".json", ".jsonl"}}
    for path in sorted(paths):
        # Conservative: even a configured but unexecuted example is excluded.
        ids = set(re.findall(r"(?<!\d)\d{19}(?!\d)", path.read_text(encoding="utf-8"))) & known_ids
        if ids:
            excluded.update(ids)
            sources.append({"path": path.as_posix(), "sha256": sha256_file(path),
                            "video_ids": sorted(ids)})
    return excluded, sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/tiktok-video-v1.json"))
    parser.add_argument("--output", type=Path, default=Path("data/manifests/reserved-eval-v1.json"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    roots = [Path("reports"), Path("configs"), Path("data/outputs")]
    excluded, sources = collect_exposure(manifest, roots)
    subset = reserve_subset(manifest, excluded)
    subset["manifest_hash"] = sha256_file(args.manifest)
    subset["exposure_scan_roots"] = [p.as_posix() for p in roots]
    subset["exposure_sources"] = sources
    content = json.dumps(subset, indent=2) + "\n"
    if args.output.exists() and args.output.read_text(encoding="utf-8") != content:
        raise ValueError("Reservation already exists; preserve it and create a reviewed new version")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Reserved {len(subset['records'])} examples across {len(subset['selected_category_counts'])} categories; excluded {len(excluded)} IDs")


if __name__ == "__main__":
    main()
