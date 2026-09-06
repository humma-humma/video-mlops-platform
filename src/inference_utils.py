import json
import statistics
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pandas as pd
from tqdm import tqdm

from src.taxonomy import format_category_options

if TYPE_CHECKING:
    from transformers import ImageTextToTextPipeline


def create_messages(
    video_path: Path,
    transcript: str,
    mode: Literal["category", "summary", "combined"] = "summary",
) -> list[dict[str, str | list[dict[str, str]]]]:
    """Create system messages for summary or category inference."""
    if mode == "summary":
        text = f"Describe this video in detail. Use the audio transcript to get more context. Audio Transcript: {transcript}"
    elif mode == "category":
        category_options = format_category_options()
        text = (
            "You are a video classification expert. Watch the video carefully and assign it to exactly one of the following categories:\n\n"
            f"{category_options}\n\n"
            "Use both the visuals and the audio transcript to determine the most relevant single category. "
            "Consider what the video is *primarily* about, not minor elements or background music. "
            "Do not include explanations or reasoning — respond with only the category name.\n\n"
            f"Audio Transcript: {transcript}"
        )
    else:
        category_options = format_category_options()
        text = (
            "Describe this video factually and assign its single primary category. "
            "Use the visual content and audio transcript. Return only a valid JSON "
            'object with exactly this schema: {"summary": "detailed factual summary", '
            '"category": "one exact category name"}. Do not use Markdown or add '
            "other keys. The category must be one of:\n\n"
            f"{category_options}\n\n"
            f"Audio Transcript: {transcript}"
        )

    return [
        {
            "role": "user",
            "content": [
                {"type": "video", "path": str(video_path)},
                {"type": "text", "text": text},
            ],
        },
    ]


def run_inference(
    pipe: "ImageTextToTextPipeline",
    messages: list[list[dict]],
    max_new_tokens: int = 140,
    mode: Literal["category", "summary", "combined"] = "category",
) -> tuple[list[str], float]:
    """Run inference and measure time."""
    start = time.perf_counter()
    if mode == "category":
        max_new_tokens = 10
    elif mode == "combined":
        max_new_tokens = 180

    output = pipe(text=messages, max_new_tokens=max_new_tokens, do_sample=False)  # type: ignore[reportCallIssue]
    text = [
        out[0]["generated_text"][-1]["content"].strip()
        for out in tqdm(output, desc="Running Inference", total=len(messages))
    ]

    return text, time.perf_counter() - start


def save_results_to_csv(res_dict: dict, csv_path: str | Path) -> pd.DataFrame:
    df = (
        pd.DataFrame.from_dict(res_dict, orient="index")
        .reset_index()
        .rename(columns={"index": "video_id"})
    )
    df.to_csv(csv_path, index=False)
    print(f"✅ Saved results to {csv_path!s}")
    return df


def save_stats_to_json(
    model_name: str,
    model_load_time: float,
    total_time: float,
    summary_time: float,
    category_time: float,
    video_count: int,
    evaluation_results: object,
    output_path: Path,
    stage_timings: dict[str, float] | None = None,
    combined_time: float = 0.0,
    inference_strategy: str = "batch_two_pass",
    per_video_timings: list[dict] | None = None,
    failures: list[dict] | None = None,
) -> None:
    per_video_timings = per_video_timings or []
    failures = failures or []

    def timing_stats(stage: str, total: float) -> dict[str, float | int | None]:
        values = [
            float(item[stage])
            for item in per_video_timings
            if item.get(stage) is not None
        ]
        return {
            "total": total,
            "mean": statistics.fmean(values)
            if values
            else (total / video_count if video_count else 0),
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "std": statistics.pstdev(values)
            if len(values) > 1
            else (0 if values else None),
            "measured_count": len(values),
        }

    stats = {
        "model_name": model_name,
        "video_count": video_count,
        "processed_video_count": len(per_video_timings)
        if inference_strategy != "batch_two_pass"
        else video_count,
        "failed_video_count": len(failures),
        "inference_strategy": inference_strategy,
        "model_load_time": model_load_time,
        "total_time": total_time,
        "stage_timings": stage_timings or {},
        "summary_inference": timing_stats("summary_time", summary_time),
        "category_inference": timing_stats("category_time", category_time),
        "combined_inference": timing_stats("combined_time", combined_time),
        "per_video_timings": per_video_timings,
        "failures": failures,
        "evaluation_results": evaluation_results,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4)
    print(f"📊 Saved statistics to {output_path!s}")
