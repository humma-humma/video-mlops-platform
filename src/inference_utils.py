import json
import time
from pathlib import Path
from typing import Literal

import pandas as pd
from transformers import ImageTextToTextPipeline


def create_messages(video_path: Path, transcript: str, mode: str = "summary"):
    """Create system messages for summary or category inference."""
    if mode == "summary":
        text = f"Describe this video in detail. Use the audio transcript to get more context. Audio Transcript: {transcript}"
    else:
        text = (
            "You are a video classification expert. Watch the video carefully and assign it to exactly one of the following categories:\n\n"
            "1. News\n"
            "2. Politics\n"
            "3. Music, Singing, & Dancing\n"
            "4. Comedy\n"
            "5. Sports\n"
            "6. Film & Animation\n"
            "7. Pets & Animals\n"
            "8. Entertainment & Shows\n"
            "9. Gaming\n"
            "10. Science & Technology\n"
            "11. Autos & Vehicles\n"
            "12. Education\n"
            "13. Outfit, Style, & Howto\n"
            "14. Nonprofits & Activism\n"
            "15. Travel & Events\n"
            "16. People & Blogs\n"
            "17. Food\n"
            "18. Relationship\n"
            "19. Family\n"
            "20. Beauty Care\n"
            "21. Daily Life\n"
            "22. Drama\n"
            "23. Lipsync\n"
            "24. Fitness & Health\n"
            "25. Society\n\n"
            "Use both the visuals and the audio transcript to determine the most relevant single category. "
            "Consider what the video is *primarily* about, not minor elements or background music. "
            "Do not include explanations or reasoning — respond with only the category name.\n\n"
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
    pipe: ImageTextToTextPipeline,
    messages: str | list[str] | list[dict],
    max_new_tokens: int = 140,
    mode: Literal["category", "summary"] = "category",
) -> tuple[list[str], float]:
    """Run inference and measure time."""
    start = time.perf_counter()
    if mode == "category":
        max_new_tokens = 64

    output = pipe(text=messages, max_new_tokens=max_new_tokens, do_sample=False)  # type:ignore[no-matching-overload]
    text = [out["generated_text"].rsplit("Assistant:", 1)[-1].strip() for out in output]

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
    evaluation_results: object,
    output_path: Path,
) -> None:
    stats = {
        "model_name": model_name,
        "model_load_time": model_load_time,
        "total_time": total_time,
        "summary_inference": {
            "mean": summary_time,
            "min": summary_time,
            "max": summary_time,
            "std": 0,
        },
        "category_inference": {
            "mean": category_time,
            "min": category_time,
            "max": category_time,
            "std": category_time,
        },
        "evaluation_results": evaluation_results,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4)
    print(f"📊 Saved statistics to {output_path!s}")
