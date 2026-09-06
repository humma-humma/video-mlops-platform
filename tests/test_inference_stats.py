import io
import json
from pathlib import Path

from src.inference_utils import save_stats_to_json


class BufferContext:
    def __init__(self, buffer: io.StringIO):
        self.buffer = buffer

    def __enter__(self) -> io.StringIO:
        return self.buffer

    def __exit__(self, *args) -> None:
        return None


def test_stats_use_real_per_video_distributions(monkeypatch) -> None:
    buffer = io.StringIO()
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: BufferContext(buffer))

    save_stats_to_json(
        model_name="fake",
        model_load_time=1.0,
        total_time=10.0,
        summary_time=6.0,
        category_time=3.0,
        combined_time=0.0,
        video_count=2,
        evaluation_results={},
        output_path=Path("unused.json"),
        inference_strategy="per_video_two_pass",
        per_video_timings=[
            {
                "video_id": "one",
                "summary_time": 2.0,
                "category_time": 1.0,
                "combined_time": None,
            },
            {
                "video_id": "two",
                "summary_time": 4.0,
                "category_time": 2.0,
                "combined_time": None,
            },
        ],
    )

    stats = json.loads(buffer.getvalue())
    assert stats["summary_inference"] == {
        "total": 6.0,
        "mean": 3.0,
        "min": 2.0,
        "max": 4.0,
        "std": 1.0,
        "measured_count": 2,
    }
    assert stats["category_inference"]["min"] == 1.0
    assert stats["combined_inference"]["min"] is None


def test_batch_stats_mark_distributions_as_unmeasured(monkeypatch) -> None:
    buffer = io.StringIO()
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: BufferContext(buffer))

    save_stats_to_json(
        model_name="fake",
        model_load_time=1.0,
        total_time=10.0,
        summary_time=6.0,
        category_time=2.0,
        video_count=2,
        evaluation_results={},
        output_path=Path("unused.json"),
    )

    stats = json.loads(buffer.getvalue())
    assert stats["summary_inference"]["mean"] == 3.0
    assert stats["summary_inference"]["min"] is None
    assert stats["summary_inference"]["measured_count"] == 0
