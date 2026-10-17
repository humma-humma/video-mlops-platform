import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from scripts.run_experiment import run_recorded_inference
from scripts import quality_suite
from src.pipeline import prepare_videos


def prepared():
    return prepare_videos([Path("a.mp4"), Path("b.mp4")], lambda *_: "",
                          lambda path, transcript, mode: [{"id": path.stem}])[0]


def test_recorded_inference_retains_outputs_and_stage_timings(tmp_path):
    journal = tmp_path / "predictions.jsonl"
    result = run_recorded_inference(prepared(), lambda messages, mode:
        (["A summary" if mode == "summary" else "Daily Life"], .5), "per_video_two_pass", journal)
    assert len(result.predictions) == 2 and not result.failures
    assert result.summary_time == result.category_time == 1
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    assert [r["video_id"] for r in records if r["record_type"] == "video_result"] == ["a", "b"]
    assert [(r["video_id"], r["stage"]) for r in records if r["record_type"] == "generation"] == [
        ("a", "summary"), ("a", "category"), ("b", "summary"), ("b", "category")]


def test_completed_video_survives_abrupt_interruption(tmp_path):
    journal = tmp_path / "predictions.jsonl"
    def inference(messages, mode):
        if messages[0][0]["id"] == "b":
            raise KeyboardInterrupt()
        return ["A summary" if mode == "summary" else "Daily Life"], .5
    with pytest.raises(KeyboardInterrupt):
        run_recorded_inference(prepared(), inference, "per_video_two_pass", journal)
    saved = [json.loads(line) for line in journal.read_text().splitlines()]
    assert len(saved) == 3 and saved[-1]["predictions"][0]["video_id"] == "a"


def test_bad_video_is_recorded_and_next_video_still_runs(tmp_path):
    def inference(messages, mode):
        if messages[0][0]["id"] == "a":
            raise ValueError("unreadable video")
        return ["A summary" if mode == "summary" else "Daily Life"], .5
    result = run_recorded_inference(prepared(), inference, "per_video_two_pass", tmp_path / "predictions.jsonl")
    assert [p.video_id for p in result.predictions] == ["b"]
    assert [f.video_id for f in result.failures] == ["a"]


def test_invalid_json_generation_survives_validation_failure(tmp_path):
    journal = tmp_path / "predictions.jsonl"
    result = run_recorded_inference(prepared()[:1], lambda *_: (["unfinished {"], 1.2),
                                    "per_video_combined", journal)
    assert result.failures and not result.predictions
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    assert records[0]["outputs"] == ["unfinished {"]
    assert records[0]["seconds"] == 1.2
    assert records[1]["failures"][0]["stage"] == "combined"


def test_killed_experiment_records_diagnostics_without_completion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def prepare(cache, output, subset, **kwargs):
        output.mkdir(parents=True)
        return [output / "baseline.json"]
    monkeypatch.setattr(quality_suite, "prepare", prepare)
    monkeypatch.setattr(quality_suite, "memory_state", lambda: {"memory.events": "oom_kill 1"})
    monkeypatch.setattr(quality_suite.subprocess, "run", Mock(side_effect=[None,
        subprocess.CalledProcessError(-9, ["python", "experiment"])]))
    with pytest.raises(subprocess.CalledProcessError):
        quality_suite.main([])
    failures = list(Path("data/outputs/quality-suite").glob("*/failure.json"))
    assert len(failures) == 1
    assert json.loads(failures[0].read_text())["returncode"] == -9
    assert not list(Path("data/outputs/quality-suite").glob("*/comparison.json"))
