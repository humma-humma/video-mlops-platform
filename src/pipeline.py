"""Testable orchestration for the batch inference pipeline."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src.category_utils import is_canonical_category, normalize_category

Mode = Literal["category", "summary", "combined"]
InferenceStrategy = Literal[
    "batch_two_pass", "per_video_two_pass", "per_video_combined"
]
Message = list[dict]
TranscriptLoader = Callable[[str, Path], str]
MessageFactory = Callable[[Path, str, Mode], Message]
InferenceFunction = Callable[[list[Message], Mode], tuple[list[str], float]]


@dataclass(frozen=True)
class PreparedVideo:
    video_id: str
    video_path: Path
    summary_message: Message
    category_message: Message
    combined_message: Message


@dataclass(frozen=True)
class VideoPrediction:
    video_id: str
    summary: str
    category: str
    summary_time: float | None = None
    category_time: float | None = None
    combined_time: float | None = None


@dataclass(frozen=True)
class VideoFailure:
    video_id: str
    stage: Mode
    error_type: str
    message: str


@dataclass(frozen=True)
class BatchPredictions:
    predictions: tuple[VideoPrediction, ...]
    summary_time: float
    category_time: float
    combined_time: float = 0.0
    failures: tuple[VideoFailure, ...] = ()
    strategy: InferenceStrategy = "batch_two_pass"

    def as_result_dict(self) -> dict[str, dict[str, str]]:
        return {
            prediction.video_id: {
                "summary": prediction.summary,
                "category": prediction.category,
            }
            for prediction in self.predictions
        }


def select_video_paths(video_folder: Path, limit: int = -1) -> tuple[Path, ...]:
    """Return video paths in deterministic filename order."""
    paths = tuple(sorted(video_folder.glob("*.mp4")))
    return paths[:limit] if limit > 0 else paths


def prepare_videos(
    video_paths: Sequence[Path],
    transcript_loader: TranscriptLoader,
    message_factory: MessageFactory,
) -> tuple[tuple[PreparedVideo, ...], float]:
    """Load transcripts and construct both prompts for each video."""
    start = time.perf_counter()
    prepared = []
    for video_path in video_paths:
        video_id = video_path.stem
        transcript = transcript_loader(video_id, video_path)
        prepared.append(
            PreparedVideo(
                video_id=video_id,
                video_path=video_path,
                summary_message=message_factory(video_path, transcript, "summary"),
                category_message=message_factory(video_path, transcript, "category"),
                combined_message=message_factory(video_path, transcript, "combined"),
            )
        )
    return tuple(prepared), time.perf_counter() - start


def run_batch_inference(
    prepared: Sequence[PreparedVideo],
    inference: InferenceFunction,
) -> BatchPredictions:
    """Run the existing two-pass batch inference behind an injectable boundary."""
    summaries, summary_time = inference(
        [video.summary_message for video in prepared], "summary"
    )
    categories, category_time = inference(
        [video.category_message for video in prepared], "category"
    )
    predictions = tuple(
        VideoPrediction(video.video_id, summary, category)
        for video, summary, category in zip(
            prepared, summaries, categories, strict=True
        )
    )
    return BatchPredictions(predictions, summary_time, category_time)


def parse_combined_output(value: str) -> tuple[str, str]:
    """Extract and validate the JSON object emitted by combined generation.

    Small models occasionally wrap an otherwise valid object in prose or a
    markdown fence.  We accept that transport noise while keeping the schema
    validation strict below.
    """
    text = value.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Recover an object embedded in an assistant prefix/suffix.  The
        # decoder determines the exact end of the object, so braces in quoted
        # strings are handled correctly.
        start = text.find("{")
        if start < 0:
            raise ValueError("Combined model output is not valid JSON") from None
        try:
            payload, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError as error:
            raise ValueError("Combined model output is not valid JSON") from error
    if not isinstance(payload, dict) or set(payload) != {"summary", "category"}:
        raise ValueError("Combined model output must contain only summary and category")

    summary = payload["summary"]
    category = payload["category"]
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Combined model output summary must be a non-empty string")
    if not isinstance(category, str) or not is_canonical_category(category):
        raise ValueError("Combined model output category is outside the taxonomy")
    return summary.strip(), normalize_category(category)


def run_isolated_inference(
    prepared: Sequence[PreparedVideo],
    inference: InferenceFunction,
    strategy: Literal["per_video_two_pass", "per_video_combined"],
    fallback_to_two_pass: bool = False,
) -> BatchPredictions:
    """Run each video independently so timings and failures are attributable."""
    predictions = []
    failures = []
    summary_total = 0.0
    category_total = 0.0
    combined_total = 0.0

    for video in prepared:
        if strategy == "per_video_combined":
            duration = 0.0
            try:
                outputs, duration = inference([video.combined_message], "combined")
                combined_total += duration
                if len(outputs) != 1:
                    raise ValueError("Combined inference returned an unexpected output count")
                summary, category = parse_combined_output(outputs[0])
                predictions.append(
                    VideoPrediction(
                        video.video_id,
                        summary,
                        category,
                        combined_time=duration,
                    )
                )
            except Exception as error:
                if fallback_to_two_pass:
                    try:
                        summaries, summary_time = inference([video.summary_message], "summary")
                        categories, category_time = inference([video.category_message], "category")
                        category = normalize_category(categories[0])
                        if not is_canonical_category(category):
                            raise ValueError("Fallback category is outside the taxonomy")
                        combined_total += summary_time + category_time
                        predictions.append(VideoPrediction(
                            video.video_id, summaries[0].strip(), category,
                            combined_time=duration + summary_time + category_time,
                        ))
                        continue
                    except Exception:
                        pass
                failures.append(
                    VideoFailure(
                        video.video_id,
                        "combined",
                        type(error).__name__,
                        str(error),
                    )
                )
            continue

        try:
            summaries, summary_time = inference([video.summary_message], "summary")
            summary_total += summary_time
            if len(summaries) != 1:
                raise ValueError("Summary inference returned an unexpected output count")
        except Exception as error:
            failures.append(
                VideoFailure(
                    video.video_id, "summary", type(error).__name__, str(error)
                )
            )
            continue

        try:
            categories, category_time = inference(
                [video.category_message], "category"
            )
            category_total += category_time
            if len(categories) != 1:
                raise ValueError("Category inference returned an unexpected output count")
            category = normalize_category(categories[0])
            if not is_canonical_category(category):
                raise ValueError("Category inference returned an out-of-taxonomy label")
        except Exception as error:
            failures.append(
                VideoFailure(
                    video.video_id, "category", type(error).__name__, str(error)
                )
            )
            continue

        predictions.append(
            VideoPrediction(
                video.video_id,
                summaries[0].strip(),
                category,
                summary_time=summary_time,
                category_time=category_time,
            )
        )

    return BatchPredictions(
        predictions=tuple(predictions),
        summary_time=summary_total,
        category_time=category_total,
        combined_time=combined_total,
        failures=tuple(failures),
        strategy=strategy,
    )
