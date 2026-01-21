from dataclasses import dataclass
from pathlib import Path


@dataclass(kw_only=True, slots=True)
class ConfigClass:
    # ===== PATHS =====
    VIDEO_FOLDER: Path
    AUDIO_FOLDER: Path
    AUDIO_TRANSCRIPT_FOLDER: Path
    GROUND_TRUTH_FILE: Path

    # ===== MODEL INFO =====
    MODEL_NAME: str
    DEVICE: str

    # ===== Output folders =====
    CSV_FOLDER: Path
    STATISTICS_FOLDER: Path

    # ===== OUTPUT FILES =====
    FILE_NAME: str
    SAMPLE_VIDEO: bool
    SAMPLE_SIZE: int

    def __post__init__(self):
        self.CSV_FOLDER.mkdir(parents=True, exist_ok=True)
        self.STATISTICS_FOLDER.mkdir(parents=True, exist_ok=True)

        self.CSV_PATH = self.CSV_FOLDER / f"{self.FILE_NAME}.csv"
        self.STAT_JSON_PATH = self.STATISTICS_FOLDER / f"{self.FILE_NAME}_stats.json"


CFG = ConfigClass(
    VIDEO_FOLDER=Path("data/inputs/videos/"),
    AUDIO_FOLDER=Path("data/inputs/audios"),
    AUDIO_TRANSCRIPT_FOLDER=Path("data/inputs/audio_transcripts/"),
    GROUND_TRUTH_FILE=Path("data/inputs/ground_truth.csv"),
    MODEL_NAME="HuggingFaceTB/SmolVLM2-2.2B-Instruct",
    DEVICE="cuda",
    CSV_FOLDER=Path("data/outputs/csv/"),
    STATISTICS_FOLDER=Path("data/outputs/statistics/"),
    FILE_NAME="smol_vlm_2.2b",
    SAMPLE_VIDEO=False,
    SAMPLE_SIZE=1,
)
