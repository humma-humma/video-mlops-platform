from copy import deepcopy

import pytest

from scripts.build_evaluation_subset import select_subset


def record(video_id, category, *, complete=True, canonical=True):
    return {"video_id": video_id, "complete_record": complete, "usable_for_category_evaluation": canonical,
            "ground_truth": {"normalized_category": category}}


def test_subset_is_stratified_and_independent_of_input_order():
    manifest = {"records": [record("a", "News"), record("b", "News"), record("c", "Sports")]}
    selected = select_subset(manifest)
    assert sorted(r["category"] for r in selected["records"]) == ["News", "Sports"]
    manifest["records"].reverse()
    assert select_subset(manifest) == selected


def test_missing_and_noncanonical_records_cannot_enter_subset():
    manifest = {"records": [record("a", "News"), record("b", "News", complete=False),
                            record("c", "Unknown", canonical=False)]}
    assert [r["video_id"] for r in select_subset(manifest)["records"]] == ["a"]


def test_rare_categories_are_not_duplicated_to_meet_target():
    manifest = {"records": [record("a", "News"), record("b", "Sports")]}
    selected = select_subset(manifest, per_category=2)
    assert len(selected["records"]) == 2
    assert "Lipsync" in selected["unrepresented_taxonomy_categories"]


def test_duplicate_ids_and_empty_eligible_inputs_are_refused():
    manifest = {"records": [record("a", "News")]}
    manifest["records"].append(deepcopy(manifest["records"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        select_subset(manifest)
    with pytest.raises(ValueError, match="No complete"):
        select_subset({"records": []})
    with pytest.raises(ValueError, match="positive"):
        select_subset(manifest, per_category=0)
