#!/bin/bash -l
#
# Initial working directory
#SBATCH -D /AIML/tinyllms/work/ETLLM/VLM-Inference
#
# Standard output and error:
#SBATCH -o slurm_outputs/baseline-%A_%a.out
#SBATCH -e slurm_outputs/baseline-%A_%a.err
#
#SBATCH --partition=a100   # Partition to run the job
#
#SBATCH --gres gpu:1       # set num GPUs per job
#
#SBATCH --mem=64G          # Request 64GB RAM
#
#SBATCH -t 00-01:30        # Maximum run-time in D-HH:MM

# Print the commands executed to the logs
set -x

export HF_HOME="/SWS/llms/nobackup"
export HF_TOKEN_PATH="~/.config/huggingface/token"

uv run main.py \
    --video-folder data/inputs/videos \
    --audio-folder data/inputs/audios \
    --audio-transcript-folder data/inputs/audio_transcripts \
    --ground-truth-file data/inputs/ground_truth.csv \
    --model-name HuggingFaceTB/SmolVLM2-2.2B-Instruct \
    --device cuda \
    --csv-folder data/outputs/csv/ \
    --statistics-folder data/outputs/statistics/ \
    --file-name smol_vlm_2.2b
