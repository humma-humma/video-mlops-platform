from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, kw_only=True)
class ConfigClass:
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
