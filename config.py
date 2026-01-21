import os
# ===== PATHS =====
VIDEO_FOLDER = 'data/inputs/videos/'
AUDIO_FOLDER = 'data/inputs/audios'
AUDIO_TRANSCRIPT_FOLDER = 'data/inputs/audio_transcripts/'
GROUND_TRUTH_FILE = "data/inputs/ground_truth.csv"

# ===== MODEL INFO =====
MODEL_NAME = "HuggingFaceTB/SmolVLM2-2.2B-Instruct"
DEVICE = "cuda"

# ===== Output folders =====
CSV_FOLDER = "data/outputs/csv/"
STATISTICS_FOLDER = "data/outputs/statistics/"

os.makedirs(CSV_FOLDER, exist_ok=True)
os.makedirs(STATISTICS_FOLDER, exist_ok=True)

# ===== OUTPUT FILES =====
FILE_NAME = f"smol_vlm_2.2b"
CSV_PATH = os.path.join(CSV_FOLDER, f"{FILE_NAME}.csv")
STAT_JSON_PATH = os.path.join(STATISTICS_FOLDER, f"{FILE_NAME}_stats.json")
SAMPLE_VIDEO = False
SAMPLE_SIZE = 1