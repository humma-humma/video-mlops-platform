from pathlib import Path

from scripts.build_dataset_manifest import build_manifest


def test_build_manifest_reports_usable_and_excluded_records() -> None:
    fixture_root = Path(__file__).parent / "fixtures" / "manifest"

    manifest = build_manifest(
        video_folder=fixture_root / "videos",
        transcript_folder=fixture_root / "audio_transcripts",
        ground_truth_file=fixture_root / "ground_truth.csv",
        dataset_root=fixture_root,
        dataset_version="test-v1",
    )

    records = {record["video_id"]: record for record in manifest["records"]}
    assert manifest["counts"] == {
        "records": 3,
        "videos": 2,
        "transcripts": 1,
        "ground_truth": 2,
        "complete_records": 1,
        "usable_for_summary_evaluation": 1,
        "usable_for_category_evaluation": 1,
        "noncanonical_ground_truth": 1,
    }
    assert records["complete"]["complete_record"]
    assert records["missing-label"]["exclusion_reasons"] == [
        "missing_transcript",
        "missing_ground_truth",
    ]
    assert records["missing-video"]["exclusion_reasons"] == [
        "missing_video",
        "missing_transcript",
    ]
    assert not records["missing-video"]["ground_truth"]["category_is_canonical"]
