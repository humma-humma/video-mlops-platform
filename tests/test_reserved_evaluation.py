from copy import deepcopy

import pytest

from scripts.build_reserved_evaluation import collect_exposure, reserve_subset
from tests.test_evaluation_subset import record


def test_reserved_selection_is_disjoint_stable_and_does_not_duplicate_rare_classes():
    manifest = {"records": [record("used", "News"), record("a", "News"),
                             record("b", "Sports"), record("c", "Sports")]}
    subset = reserve_subset(manifest, {"used"})
    assert {r["video_id"] for r in subset["records"]} == {"a", "b", "c"}
    assert subset["categories_below_target"] == {"News": 1, "Sports": 2}
    manifest["records"].reverse()
    assert reserve_subset(manifest, {"used"}) == subset
    assert "historical exposure unknown" in subset["exposure_status"]
    assert "not an acceptance set" in subset["acceptance_status"]


def test_duplicate_excluded_records_are_still_invalid():
    row = record("used", "News")
    with pytest.raises(ValueError, match="Duplicate"):
        reserve_subset({"records": [row, deepcopy(row), record("new", "Sports")]}, {"used"})


def test_exposure_scan_includes_configured_and_failed_examples(tmp_path):
    used, failed, unrelated = "1234567890123456789", "2234567890123456789", "3234567890123456789"
    manifest = {"records": [record(used, "News"), record(failed, "Sports")]}
    (tmp_path / "config.json").write_text('{"video_ids": ["' + used + '", "' + unrelated + '"]}')
    (tmp_path / "journal.jsonl").write_text('{"video_id": "' + failed + '", "error": "killed"}\n')
    excluded, sources = collect_exposure(manifest, [tmp_path])
    assert excluded == {used, failed}
    assert len(sources) == 2
    assert all(len(source["sha256"]) == 64 for source in sources)
