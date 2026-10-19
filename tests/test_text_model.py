import json
import pytest
from pydantic import ValidationError

from scripts.train_text_topic import build_model
from src.service.deployments import TextTopicAdapter
from src.service import text_model
from src.service.lifecycle import classify_failure
from src.service.text_model import MODEL_PATH, ModelArtifactUnavailable, predict


def test_committed_model_artifact_is_reproducible_and_distinct_from_video():
    assert json.loads(MODEL_PATH.read_text(encoding="utf-8")) == build_model()
    for text, expected in (("Bake bread in the oven", "cooking"),
                           ("The football team scored a goal", "sports"),
                           ("The server runs Python code", "technology")):
        label, scores, revision = predict(text)
        assert label == expected
        assert len(revision) == 64
        assert abs(sum(scores.values()) - 1) < 1e-9


def test_text_adapter_validates_its_own_output():
    adapter = TextTopicAdapter()
    label, scores, revision = predict("Bake bread in the oven")
    result = {"schema_version": "1", "deployment_id": adapter.deployment_id,
              "model_version": "toy-text-topic-naive-bayes-v1", "model_revision": revision,
              "output": {"label": label, "scores": scores}, "timings": {"inference_total": 0.1}}
    assert adapter.validate_result(result)["output"]["label"] == "cooking"
    result["output"]["scores"] = {"cooking": 1.0}
    with pytest.raises(ValidationError):
        adapter.validate_result(result)


def test_missing_packaged_model_is_not_classified_as_missing_job_input(monkeypatch):
    monkeypatch.setattr(text_model, "MODEL_PATH", MODEL_PATH.with_name("absent-test-model.json"))
    text_model.load_model.cache_clear()
    try:
        with pytest.raises(ModelArtifactUnavailable) as caught:
            text_model.predict("The server runs Python")
        assert classify_failure(caught.value)[0] == "model_artifact_unavailable"
        assert classify_failure(FileNotFoundError("Input artifact is missing"))[0] == "missing_input"
    finally:
        text_model.load_model.cache_clear()
