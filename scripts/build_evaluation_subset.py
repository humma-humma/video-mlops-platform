"""Select a fixed development subset before looking at model predictions."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from src.lineage import canonical_hash, sha256_file
from src.taxonomy import CATEGORIES


def select_subset(manifest: dict, per_category: int = 1, seed: str = "video-mlops-eval-v1") -> dict:
    if per_category < 1:
        raise ValueError("per_category must be positive")
    groups = defaultdict(list)
    seen = set()
    for record in manifest["records"]:
        video_id = record["video_id"]
        if video_id in seen:
            raise ValueError("Duplicate manifest video ID")
        seen.add(video_id)
        if record["complete_record"] and record["usable_for_category_evaluation"]:
            category = record["ground_truth"]["normalized_category"]
            if category not in CATEGORIES:
                raise ValueError("Manifest category disagrees with taxonomy")
            groups[category].append(video_id)
    selected = []
    for category, video_ids in sorted(groups.items()):
        ordered = sorted(video_ids, key=lambda video_id: (hashlib.sha256(f"{seed}:{video_id}".encode()).hexdigest(), video_id))
        selected.extend({"video_id": video_id, "category": category} for video_id in ordered[:per_category])
    if not selected:
        raise ValueError("No complete canonical records available")
    selected.sort(key=lambda record: record["video_id"])
    return {"schema_version": "1", "subset_version": "development-eval-v1", "seed": seed,
            "purpose": "stratified development comparison; not a production quality acceptance set",
            "per_category": per_category, "records": selected,
            "sample_hash": canonical_hash([record["video_id"] for record in selected]),
            "available_category_counts": {key: len(value) for key, value in sorted(groups.items())},
            "unrepresented_taxonomy_categories": sorted(set(CATEGORIES) - set(groups))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/tiktok-video-v1.json"))
    parser.add_argument("--output", type=Path, default=Path("data/manifests/development-eval-v1.json"))
    parser.add_argument("--per-category", type=int, default=1)
    args = parser.parse_args()
    subset = select_subset(json.loads(args.manifest.read_text(encoding="utf-8")), args.per_category)
    subset["manifest_hash"] = sha256_file(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(subset, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(subset['records'])}-video subset: {args.output}")


if __name__ == "__main__":
    main()
