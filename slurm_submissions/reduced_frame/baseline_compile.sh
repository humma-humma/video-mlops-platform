#!/bin/bash -l
#
# Initial working directory
#SBATCH -D /AIML/tinyllms/work/ETLLM/VLM-Inference
#
# Standard output and error:
#SBATCH -o slurm_outputs/baseline_pipeline_compile_reduced_frames-%A_%a.out
#SBATCH -e slurm_outputs/baseline_pipeline_compile_reduced_frames-%A_%a.err
#
#SBATCH --partition=a100   # Partition to run the job
#
#SBATCH --gres gpu:1       # set num GPUs per job
#
#SBATCH --mem=64G          # Request 64GB RAM
#
#SBATCH -t 00-04:00        # Maximum run-time in D-HH:MM

# Print the commands executed to the logs
set -x

export HF_HOME="/SWS/llms/nobackup"
export HF_TOKEN_PATH="~/.config/huggingface/token"

INPUT_DATA_DIR="data/inputs"
OUTPUT_DATA_DIR="data/outputs"

export TORCHINDUCTOR_CACHE_DIR="/AIML/tinyllms/nobackup/.inductor_cache"
export PYTORCH_ALLOC_CONF="backend:cudaMallocAsync"

uv run main.py \
    --video-folder $INPUT_DATA_DIR/videos \
    --audio-folder $INPUT_DATA_DIR/audios \
    --audio-transcript-folder $INPUT_DATA_DIR/audio_transcripts \
    --ground-truth-file $INPUT_DATA_DIR/ground_truth.csv \
    --model-name HuggingFaceTB/SmolVLM2-2.2B-Instruct \
    --torch-compile \
    --num-workers 4 \
    --max-frames 16 \
    --csv-folder $OUTPUT_DATA_DIR/csv/ \
    --statistics-folder $OUTPUT_DATA_DIR/statistics/ \
    --file-name smol_vlm_2.2b_pipeline_compile_reduced_frames
