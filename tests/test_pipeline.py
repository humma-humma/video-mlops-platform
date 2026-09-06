from pathlib import Path

import pytest

from src.pipeline import (
    parse_combined_output,
    prepare_videos,
    run_batch_inference,
    run_isolated_inference,
    select_video_paths,
)


def test_select_video_paths_is_sorted_and_limited() -> None:
    video_folder = Path(__file__).parent / "fixtures" / "pipeline" / "videos"

    assert [path.name for path in select_video_paths(video_folder)] == [
        "a.mp4",
        "b.mp4",
    ]
    assert [path.name for path in select_video_paths(video_folder, 1)] == ["a.mp4"]


def test_pipeline_orchestration_accepts_fake_dependencies() -> None:
    paths = [Path("b.mp4"), Path("a.mp4")]

    prepared, preparation_time = prepare_videos(
        paths,
        transcript_loader=lambda video_id, _: f"transcript-{video_id}",
        message_factory=lambda path, transcript, mode: [
            {"path": str(path), "text": transcript, "mode": mode}
        ],
    )

    def fake_inference(messages, mode):
        return [f"{mode}-{message[0]['path']}" for message in messages], 1.5

    result = run_batch_inference(prepared, fake_inference)

    assert preparation_time >= 0
    assert result.summary_time == 1.5
    assert result.category_time == 1.5
    assert result.as_result_dict() == {
        "b": {"summary": "summary-b.mp4", "category": "category-b.mp4"},
        "a": {"summary": "summary-a.mp4", "category": "category-a.mp4"},
    }


def test_pipeline_rejects_missing_model_outputs() -> None:
    prepared, _ = prepare_videos(
        [Path("video.mp4")],
        transcript_loader=lambda *_: "transcript",
        message_factory=lambda *_: [{}],
    )

    with pytest.raises(ValueError):
        run_batch_inference(prepared, lambda messages, mode: ([], 0.0))


def test_parse_combined_output_validates_and_normalizes_schema() -> None:
    summary, category = parse_combined_output(
        '```json\n{"summary": "A factual summary", '
        '"category": "entertainment and shows"}\n```'
    )

    assert summary == "A factual summary"
    assert category == "Entertainment & Shows"

    summary, category = parse_combined_output(
        'Here is the result:\n{"summary": "A factual summary", '
        '"category": "News"}\n'
    )
    assert summary == "A factual summary"
    assert category == "News"


@pytest.mark.parametrize(
    "output",
    [
        "not json",
        '{"summary": "ok", "category": "Business"}',
        '{"summary": "ok", "category": "News", "reason": "extra"}',
        '{"summary": "", "category": "News"}',
    ],
)
def test_parse_combined_output_rejects_invalid_results(output: str) -> None:
    with pytest.raises(ValueError):
        parse_combined_output(output)


def test_isolated_combined_inference_records_timings_and_failures() -> None:
    prepared, _ = prepare_videos(
        [Path("good.mp4"), Path("bad.mp4")],
        transcript_loader=lambda *_: "transcript",
        message_factory=lambda path, transcript, mode: [{"path": str(path)}],
    )

    def fake_inference(messages, mode):
        if messages[0][0]["path"] == "bad.mp4":
            return ["invalid"], 2.0
        return ['{"summary": "summary", "category": "News"}'], 1.25

    result = run_isolated_inference(prepared, fake_inference, "per_video_combined")

    assert result.combined_time == 3.25
    assert result.predictions[0].combined_time == 1.25
    assert result.failures[0].video_id == "bad"
    assert result.failures[0].stage == "combined"


def test_isolated_two_pass_inference_attributes_category_failure() -> None:
    prepared, _ = prepare_videos(
        [Path("video.mp4")],
        transcript_loader=lambda *_: "transcript",
        message_factory=lambda *_: [{}],
    )

    def fake_inference(messages, mode):
        return (["summary"] if mode == "summary" else ["Business"]), 0.5

    result = run_isolated_inference(prepared, fake_inference, "per_video_two_pass")

    assert not result.predictions
    assert result.summary_time == 0.5
    assert result.category_time == 0.5
    assert result.failures[0].stage == "category"
