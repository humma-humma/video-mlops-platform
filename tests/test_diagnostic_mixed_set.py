"""The retrospective case set must retain its source labels and evidence."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports" / "diagnostics"


def test_mixed_set_preserves_source_cases_and_recorded_evaluation():
    manifest_path = REPORTS / "mixed_cases_v1.json"
    manifest = json.loads(manifest_path.read_text())
    evaluation = json.loads((REPORTS / "mixed_evaluation_v1.json").read_text())

    assert evaluation["case_manifest_sha256"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert evaluation["rules_sha256"] == "738f38f1a5d6ea0e95b50e8789842f62db1ef79cc314ff7df1e56dc63ee131e2"
    assert len({case["id"] for case in manifest["cases"]}) == len(manifest["cases"]) == 12
    assert len({case["incident_group"] for case in manifest["cases"]}) == 7

    source_fields = ("id", "expected", "split", "origin")
    for case, result in zip(manifest["cases"], evaluation["cases"], strict=True):
        source = json.loads((REPORTS / case["source_manifest"]).read_text())
        original = next(item for item in source["cases"] if item["id"] == case["id"])
        assert all(case[field] == original[field] for field in source_fields)
        assert Path(case["bundle"]).name == original["bundle"]
        bundle = json.loads((REPORTS / case["bundle"]).read_text())
        assert result["bundle_sha256"] == bundle["bundle_sha256"]
        assert result["case_id"] == case["id"]
        assert result["expected"] == case["expected"]
        assert result["correct"] and result["citations_valid"]

    assert evaluation["correct"] == evaluation["total"] == 12
    assert evaluation["abstentions"] == 8
    assert evaluation["correct_abstentions"] == 8
    assert evaluation["cited_cases"] == 4
    assert evaluation["supported_diagnoses"] == evaluation["correct_diagnoses"] == 4
    assert evaluation["missed_diagnoses"] == 0
    assert evaluation["false_confident"] == 0
