from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional


@dataclass(frozen=True, kw_only=True)
class InferenceConfig:
    # ===== PATHS =====
    video_folder: Path = field(metadata={"help": "Path to folder with video files"})
    audio_folder: Path = field(metadata={"help": "Path to folder with audio files"})
    audio_transcript_folder: Path = field(
        metadata={"help": "Path to folder with audio transcript files"},
    )
    ground_truth_file: Path = field(
        metadata={"help": "Path to ground truth file (CSV)"},
    )

    # ===== MODEL INFO =====
    model_name: str = field(metadata={"help": "Name of the model to be used"})
    use_kv_cache: bool = field(
        default=False,
        metadata={"help": "Whether to use key-value cache for faster inference."},
    )
    torch_compile: bool = field(
        default=False,
        metadata={"help": "Whether to compile the model for faster inference."},
    )
    attention_implementation: Optional[str] = field(
        default=None,
        metadata={
            "help": "Attention implementation to use. If None, the default implementation is used.",
        },
    )
    batch_size: int = field(
        default=1,
        metadata={"help": "Batch size for inference."},
    )
    num_workers: int = field(
        default=0,
        metadata={"help": "Number of worker threads for data loading."},
    )
    max_frames: Optional[int] = field(
        default=None,
        metadata={"help": "Maximum number of frames to process from each video."},
    )
    whisper_device_id: int = field(
        default=0,
        metadata={"help": "CUDA device ID for Whisper transcript fallback."},
    )
    inference_strategy: Literal[
        "batch_two_pass", "per_video_two_pass", "per_video_combined"
    ] = field(
        default="batch_two_pass",
        metadata={
            "help": "Batch throughput mode or isolated per-video timing strategy."
        },
    )
    model_dtype: Literal["auto", "float16", "bfloat16"] = field(
        default="auto",
        metadata={"help": "Model dtype; auto selects a supported CUDA dtype."},
    )

    # ===== Output folders =====
    csv_folder: Path = field(metadata={"help": "Path to folder to save CSV outputs"})
    statistics_folder: Path = field(
        metadata={"help": "Path to folder to save statistics outputs"},
    )

    # ===== OUTPUT FILES =====
    file_name: str = field(metadata={"help": "Base name for output files"})
    num_video_samples: int = field(
        default=-1,
        metadata={
            "help": "Number of video samples to process. Specify a number more than 0 to limit the samples.",
        },
    )

    def __post_init__(self):
        self.csv_folder.mkdir(parents=True, exist_ok=True)
        self.statistics_folder.mkdir(parents=True, exist_ok=True)
