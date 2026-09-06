from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from dataclasses import asdict
from pathlib import Path

os.environ.setdefault("VIDEO_DECODING_BACKEND", "torchvision")
os.environ.setdefault("TRANSFORMERS_VIDEO_BACKEND", "torchvision")

from src.config import InferenceConfig
from src.pipeline import prepare_videos, run_isolated_inference


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bounded real-GPU smoke test")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument(
        "--model-name",
        default="HuggingFaceTB/SmolVLM2-500M-Video-Instruct",
    )
    parser.add_argument("--max-frames", type=int, default=4)
    parser.add_argument(
        "--output", type=Path, default=Path("reports/gpu_smoke.json")
    )
    args = parser.parse_args()

    if not args.video.is_file():
        raise FileNotFoundError(f"Video does not exist: {args.video}")
    if not args.transcript.is_file():
        raise FileNotFoundError(f"Transcript does not exist: {args.transcript}")

    import torch
    import transformers

    from src.inference_utils import create_messages, run_inference
    from src.model_utils import load_model

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available")

    cfg = InferenceConfig(
        video_folder=args.video.parent,
        audio_folder=Path("data/inputs/audios"),
        audio_transcript_folder=args.transcript.parent,
        ground_truth_file=Path("data/inputs/ground_truth.csv"),
        model_name=args.model_name,
        max_frames=args.max_frames,
        csv_folder=Path("data/outputs/csv"),
        statistics_folder=Path("data/outputs/statistics"),
        file_name="gpu_smoke",
        inference_strategy="per_video_two_pass",
        model_dtype="auto",
    )

    torch.cuda.reset_peak_memory_stats()
    pipe, model_load_time = load_model(cfg)
    prepared, preparation_time = prepare_videos(
        [args.video],
        transcript_loader=lambda *_: args.transcript.read_text(
            encoding="utf-8"
        ).strip(),
        message_factory=lambda path, transcript, mode: create_messages(
            path, transcript, mode=mode
        ),
    )
    inference = lambda messages, mode: run_inference(pipe, messages, mode=mode)

    runs = {}
    for strategy in ("per_video_two_pass", "per_video_combined"):
        result = run_isolated_inference(
            prepared, inference, strategy, fallback_to_two_pass=True
        )
        runs[strategy] = {
            "summary_time": result.summary_time,
            "category_time": result.category_time,
            "combined_time": result.combined_time,
            "predictions": [asdict(item) for item in result.predictions],
            "failures": [asdict(item) for item in result.failures],
        }

    config = pipe.model.config
    report = {
        "purpose": "economic real-GPU smoke test; not the 2.2B production baseline",
        "video_id": args.video.stem,
        "model_name": args.model_name,
        "model_revision": getattr(config, "_commit_hash", None),
        "max_frames": args.max_frames,
        "model_load_time": model_load_time,
        "input_preparation_time": preparation_time,
        "peak_gpu_memory_bytes": torch.cuda.max_memory_allocated(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "gpu": torch.cuda.get_device_name(0),
        },
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote GPU smoke report to {args.output}")


if __name__ == "__main__":
    main()
