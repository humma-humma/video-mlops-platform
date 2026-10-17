from copy import deepcopy

import pytest
from pydantic import ValidationError

from src.experiments import ExperimentConfig, GatePolicy, evaluate_gate
from src.lineage import canonical_hash


def baseline():
    return {"purpose": "candidate_evaluation", "sample_count": 10, "category_evaluated_count": 10, "quality_status": "complete",
            "summary_metric_hash": "b" * 64,
            "lineage": {key: "a" * (40 if key in ("model_revision", "processor_revision") else 64) for key in ("model_revision", "processor_revision", "manifest_hash",
                "code_hash", "prompt_hash", "taxonomy_hash", "inference_config_hash", "sample_hash")},
            "environment": {"gpu": "test-device", "torch": "test-version", "transformers": "test-version"},
            "metrics": {"bertscore_f1": .9, "category_accuracy": .8, "error_rate": 0,
                        "latency_p95_seconds": 10, "peak_gpu_memory_bytes": 100}}


def policy(report):
    return GatePolicy(baseline_hash=canonical_hash(report), reviewed_by="synthetic-test-fixture",
                      minimum_samples=10, minimum_category_samples=10, max_bertscore_drop=.01, max_accuracy_drop=.01,
                      max_error_rate=0, max_latency_ratio=1.1, max_gpu_memory_ratio=1.1)


def test_unchanged_candidate_passes_without_mutating_baseline():
    report = baseline()
    original = deepcopy(report)
    assert evaluate_gate(report, report, policy(report))["passed"]
    assert original == report


@pytest.mark.parametrize("metric,value", [
    ("bertscore_f1", .5), ("category_accuracy", .2), ("error_rate", .1),
    ("latency_p95_seconds", 20), ("peak_gpu_memory_bytes", 200),
    ("bertscore_f1", None), ("bertscore_f1", float("nan")), ("bertscore_f1", True),
])
def test_degraded_or_missing_measurements_fail(metric, value):
    report = baseline()
    candidate = deepcopy(report)
    candidate["metrics"][metric] = value
    if isinstance(value, float) and value != value:
        # Invalid JSON is refused before a report can even receive a content hash.
        with pytest.raises(ValueError):
            evaluate_gate(candidate, report, policy(report))
    else:
        assert not evaluate_gate(candidate, report, policy(report))["passed"]


def test_changed_baseline_and_smoke_results_fail():
    report = baseline()
    reviewed = policy(report)
    report["metrics"]["bertscore_f1"] = .5
    assert not evaluate_gate(report, report, reviewed)["passed"]
    report["purpose"] = "smoke"
    assert not evaluate_gate(report, report, policy(report))["passed"]


def test_dataset_or_runtime_changes_fail_comparison():
    report = baseline()
    for field in ("lineage", "environment"):
        candidate = deepcopy(report)
        candidate[field] = {}
        assert not evaluate_gate(candidate, report, policy(report))["passed"]


def test_config_rejects_unknown_keys_floating_revisions_and_duplicate_ids():
    values = dict(name="test", model_name="test", model_revision="a" * 40, video_ids=["b", "a"])
    assert ExperimentConfig(**values).video_ids == ["a", "b"]
    for overrides in ({"unknown": True}, {"model_revision": "main"}, {"video_ids": ["a", "a"]}):
        with pytest.raises(ValidationError):
            ExperimentConfig(**(values | overrides))


def test_tracking_records_the_comparison_without_promoting_it():
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from src.tracking import track_candidate
    sdk = MagicMock()
    sdk.start_run.return_value.__enter__.return_value = SimpleNamespace(info=SimpleNamespace(run_id="test-run"))
    report = baseline()
    result = track_candidate(report, report, policy(report), tracking_uri="http://tracking.test", mlflow_module=sdk)
    assert result["run_id"] == "test-run"
    assert sdk.log_dict.call_count == 5
    sdk.MlflowClient.assert_not_called()


@pytest.mark.parametrize("failed,digest", [(True, "sha256:" + "a" * 64), (False, "latest")])
def test_registration_refuses_failed_gates_and_mutable_images(failed, digest):
    from unittest.mock import MagicMock
    from src.tracking import track_candidate
    report = baseline()
    candidate = deepcopy(report)
    if failed:
        candidate["metrics"]["error_rate"] = .5
    sdk = MagicMock()
    with pytest.raises(ValueError):
        track_candidate(candidate, report, policy(report), tracking_uri="http://tracking.test",
                        registry_name="test-bundle", image_digest=digest, mlflow_module=sdk)
    assert not sdk.mock_calls


def test_registration_records_image_and_gate_digests():
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from src.tracking import track_candidate
    sdk = MagicMock()
    sdk.start_run.return_value.__enter__.return_value = SimpleNamespace(info=SimpleNamespace(run_id="test-run"))
    sdk.MlflowClient.return_value.create_model_version.return_value.version = "1"
    report = baseline()
    result = track_candidate(report, report, policy(report), tracking_uri="http://tracking.test",
        registry_name="test-bundle", image_digest="sha256:" + "a" * 64, mlflow_module=sdk)
    assert result["registry_version"] == "1"
    kwargs = sdk.MlflowClient.return_value.create_model_version.call_args.kwargs
    assert kwargs["source"] == "runs:/test-run/bundle"
    assert kwargs["tags"]["candidate_hash"] == canonical_hash(report)
    sdk.MlflowClient.return_value.set_registered_model_alias.assert_not_called()
