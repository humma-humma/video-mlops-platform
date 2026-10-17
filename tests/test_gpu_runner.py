from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.service import inference


def runner(output=None):
    pipe = SimpleNamespace(model=SimpleNamespace(config=SimpleNamespace(_commit_hash="revision")))
    generate = Mock(side_effect=lambda messages, mode: (
        [output if output is not None else ("A factual summary" if mode == "summary" else "Daily Life")], 0.5,
    ))
    instance = inference.GPUModelRunner(
        pipe, "test-model", 2.0,
        lambda path, transcript, mode: [{"path": str(path), "transcript": transcript}],
        generate,
    )
    return instance, generate


def test_runner_reports_real_metadata_and_warm_reuse():
    instance, generate = runner()
    first = instance.run(Path("video.mp4"), "supplied transcript")
    second = instance.run(Path("video.mp4"), "supplied transcript")
    assert first["model_version"] == "test-model"
    assert first["model_revision"] == "revision"
    assert first["model_instance_id"] == second["model_instance_id"]
    assert first["transcript_source"] == "provided"
    assert first["timings"]["model_load"] == 2.0
    assert second["timings"]["model_load"] == 0.0
    assert generate.call_count == 4


def test_runner_does_not_report_invalid_category_as_success():
    instance, _ = runner("Business")
    with pytest.raises(RuntimeError, match="GPU inference failed at category"):
        instance.run(Path("video.mp4"), "")


def test_runner_rejects_empty_summary():
    instance, generate = runner()
    generate.side_effect = lambda messages, mode: (["" if mode == "summary" else "Daily Life"], 0.1)
    with pytest.raises(ValueError, match="empty summary"):
        instance.run(Path("video.mp4"), "")


def test_model_factory_is_cached_per_process(monkeypatch):
    inference.get_model_runner.cache_clear()
    factory = Mock(return_value=object())
    monkeypatch.setattr(inference, "create_model_runner", factory)
    try:
        assert inference.get_model_runner() is inference.get_model_runner()
        factory.assert_called_once()
    finally:
        inference.get_model_runner.cache_clear()
