"""Lazy, process-scoped GPU runner; importing this module does not load Torch."""

from functools import lru_cache
from pathlib import Path
import time
from uuid import uuid4

from src.pipeline import prepare_videos, run_isolated_inference
from src.taxonomy import TAXONOMY_VERSION
from src.lineage import canonical_hash, source_lineage


class GPUModelRunner:
    def __init__(self, pipe, model_name, model_load_time, message_factory, inference):
        self.pipe = pipe
        self.model_name = model_name
        self.model_revision = getattr(pipe.model.config, "_commit_hash", None)
        self.model_load_time = model_load_time
        self.message_factory = message_factory
        self.inference = inference
        self.instance_id = str(uuid4())
        self.calls = 0
        self.lineage = source_lineage()

    def run(self, video_path: Path, transcript: str) -> dict:
        start = time.perf_counter()
        cold = self.calls == 0
        self.calls += 1
        prepared, preparation_time = prepare_videos(
            [video_path], transcript_loader=lambda *_: transcript,
            message_factory=self.message_factory,
        )
        result = run_isolated_inference(prepared, self.inference, "per_video_two_pass")
        if result.failures:
            failure = result.failures[0]
            raise RuntimeError(f"GPU inference failed at {failure.stage}: {failure.error_type}")
        prediction = result.predictions[0]
        if not prediction.summary.strip():
            raise ValueError("GPU inference returned an empty summary")
        return {
            "schema_version": "1", "video_id": video_path.stem,
            "summary": prediction.summary, "category": prediction.category,
            "model_version": self.model_name, "model_revision": self.model_revision,
            "lineage": self.lineage,
            "taxonomy_version": TAXONOMY_VERSION,
            "model_instance_id": self.instance_id,
            "transcript_source": "provided" if transcript else "none",
            "timings": {
                "model_load": self.model_load_time if cold else 0.0,
                "input_preparation": preparation_time,
                "summary": result.summary_time, "category": result.category_time,
                "inference_total": time.perf_counter() - start,
            },
        }


def create_model_runner(model_name: str, model_revision: str, max_frames: int, scratch_root: str):
    import os

    import torch
    from src.config import InferenceConfig
    from src.inference_utils import create_messages, run_inference
    from src.model_utils import load_model

    if not torch.cuda.is_available():
        raise RuntimeError("Real inference requires a CUDA GPU")
    if max_frames < 1:
        raise ValueError("max_frames must be positive")
    root = Path(scratch_root)
    cfg = InferenceConfig(
        video_folder=root, audio_folder=root, audio_transcript_folder=root,
        ground_truth_file=root / "unused.csv", csv_folder=root,
        statistics_folder=root, file_name="worker",
        model_name=model_name, model_revision=model_revision, max_frames=max_frames,
        model_dtype="auto", use_kv_cache=True,
    )
    pipe, load_time = load_model(cfg)
    runner = GPUModelRunner(
        pipe, model_name, load_time, create_messages,
        lambda messages, mode: run_inference(pipe, messages, mode=mode),
    )
    if runner.model_revision != model_revision:
        raise RuntimeError("Loaded model revision differs from the pinned revision")
    resolved = {"model_name": model_name, "model_revision": model_revision,
                "processor_revision": model_revision, "max_frames": max_frames,
                "model_dtype": "auto", "use_kv_cache": True,
                "inference_strategy": "per_video_two_pass",
                "decoder": "torchcodec" if os.environ.get("VIDEO_REQUIRE_TORCHCODEC") == "1" else "processor-default"}
    runner.lineage.update(inference_config=resolved, inference_config_hash=canonical_hash(resolved))
    return runner


@lru_cache(maxsize=1)
def get_model_runner():
    # Called inside a Celery child, so the parent never initializes CUDA before fork.
    from .config import settings

    return create_model_runner(
        settings.model_name, settings.model_revision, settings.max_frames,
        settings.worker_scratch_root,
    )
