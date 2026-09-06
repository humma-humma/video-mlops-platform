from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from src.category_utils import is_canonical_category, normalize_category
from src.taxonomy import TAXONOMY_VERSION


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_ground_truth(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    required_columns = {"video_id", "summary", "category"}
    if not rows or not required_columns.issubset(rows[0]):
        raise ValueError(
            f"Ground truth must contain columns: {sorted(required_columns)}"
        )

    result: dict[str, dict[str, str]] = {}
    for row in rows:
        video_id = row["video_id"].strip()
        if video_id in result:
            raise ValueError(f"Duplicate ground-truth video_id: {video_id}")
        result[video_id] = row
    return result


def file_metadata(path: Path, root: Path) -> dict[str, str | int]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def build_manifest(
    video_folder: Path,
    transcript_folder: Path,
    ground_truth_file: Path,
    dataset_root: Path,
    dataset_version: str,
) -> dict:
    if not video_folder.is_dir():
        raise FileNotFoundError(f"Video folder does not exist: {video_folder}")
    if not transcript_folder.is_dir():
        raise FileNotFoundError(
            f"Transcript folder does not exist: {transcript_folder}"
        )
    if not ground_truth_file.is_file():
        raise FileNotFoundError(
            f"Ground-truth file does not exist: {ground_truth_file}"
        )

    videos = {path.stem: path for path in video_folder.glob("*.mp4")}
    transcripts = {path.stem: path for path in transcript_folder.glob("*.txt")}
    ground_truth = load_ground_truth(ground_truth_file)
    video_ids = sorted(set(videos) | set(transcripts) | set(ground_truth))

    records = []
    for video_id in video_ids:
        video_path = videos.get(video_id)
        transcript_path = transcripts.get(video_id)
        truth = ground_truth.get(video_id)
        reasons = []
        if video_path is None:
            reasons.append("missing_video")
        if transcript_path is None:
            reasons.append("missing_transcript")
        if truth is None:
            reasons.append("missing_ground_truth")

        category = truth["category"].strip() if truth else None
        normalized_category = normalize_category(category) if category else None
        category_is_canonical = is_canonical_category(category) if truth else False
        records.append(
            {
                "video_id": video_id,
                "complete_record": not reasons,
                "usable_for_summary_evaluation": video_path is not None
                and truth is not None,
                "usable_for_category_evaluation": video_path is not None
                and truth is not None
                and category_is_canonical,
                "exclusion_reasons": reasons,
                "video": file_metadata(video_path, dataset_root)
                if video_path
                else None,
                "transcript": file_metadata(transcript_path, dataset_root)
                if transcript_path
                else None,
                "ground_truth": {
                    "category": category,
                    "normalized_category": normalized_category,
                    "category_is_canonical": category_is_canonical,
                }
                if truth
                else None,
            }
        )

    return {
        "schema_version": "1",
        "dataset_version": dataset_version,
        "taxonomy_version": TAXONOMY_VERSION,
        "ground_truth": file_metadata(ground_truth_file, dataset_root),
        "counts": {
            "records": len(records),
            "videos": len(videos),
            "transcripts": len(transcripts),
            "ground_truth": len(ground_truth),
            "complete_records": sum(record["complete_record"] for record in records),
            "usable_for_summary_evaluation": sum(
                record["usable_for_summary_evaluation"] for record in records
            ),
            "usable_for_category_evaluation": sum(
                record["usable_for_category_evaluation"] for record in records
            ),
            "noncanonical_ground_truth": sum(
                record["ground_truth"] is not None
                and not record["ground_truth"]["category_is_canonical"]
                for record in records
            ),
        },
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a versioned dataset manifest")
    parser.add_argument(
        "--dataset-root", type=Path, default=Path("data/inputs")
    )
    parser.add_argument("--video-folder", type=Path)
    parser.add_argument("--transcript-folder", type=Path)
    parser.add_argument("--ground-truth-file", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("data/manifests/tiktok-video-v1.json")
    )
    parser.add_argument("--dataset-version", default="tiktok-video-v1")
    args = parser.parse_args()

    video_folder = args.video_folder or args.dataset_root / "videos"
    transcript_folder = (
        args.transcript_folder or args.dataset_root / "audio_transcripts"
    )
    ground_truth_file = (
        args.ground_truth_file or args.dataset_root / "ground_truth.csv"
    )
    manifest = build_manifest(
        video_folder=video_folder,
        transcript_folder=transcript_folder,
        ground_truth_file=ground_truth_file,
        dataset_root=args.dataset_root,
        dataset_version=args.dataset_version,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote dataset manifest to {args.output}")


if __name__ == "__main__":
    main()
