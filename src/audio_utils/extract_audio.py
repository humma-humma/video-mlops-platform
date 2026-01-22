from pathlib import Path

import torch
from moviepy import VideoFileClip
from transformers import pipeline


def extract_audio_mp3(video_path: Path, video_id: str, output_folder: Path) -> None:
    """Extracts audio from a video file and saves it as an MP3 using MoviePy.

    Args:
        video_path (str): Path to the input video file.
        output_folder (str): Folder to save the extracted MP3 audio file.

    """
    output_folder.mkdir(parents=True, exist_ok=True)
    output_audio_path = output_folder / f"{video_id}.mp3"

    with VideoFileClip(str(video_path)) as video_clip:
        if video_clip.audio is None:
            print(
                f"Warning: Video {video_path!s} has no audio track. Skipping audio extraction.",
            )
            return

        # Extract and write the audio file
        # codec='mp3' is often implicit with.mp3 extension but can be specified
        # bitrate='192k' or similar can be added for quality control if needed
        video_clip.audio.write_audiofile(str(output_audio_path))

    print(f"Successfully extracted audio to {output_audio_path!s}")


# Optional: Use this function to extract audio from a video file
# Example usage:
# video_file = "path/to/your/tiktok_video.mp4"
# output_dir = "path/to/output/audio"
# extract_audio_mp3(video_file, output_dir)


def transcribe_audio_whisper(
    audio_path: Path,
    video_id: str,
    output_folder: Path,
    model_name: str = "openai/whisper-large-v3",
    device_id: int = 0,
) -> None:
    """Transcribes an audio file using the Whisper model via Hugging Face pipeline.

    Args:
        audio_path (str): Path to the input audio file (e.g., MP3, WAV).
        output_folder (str): Folder to save the transcription text file.
        model_name (str): The Whisper model checkpoint name.
        device_id (int): The GPU device ID to use.

    """
    output_folder.mkdir(parents=True, exist_ok=True)
    output_txt_path = output_folder / f"{video_id}.txt"

    if not output_txt_path.is_file():
        print(f"Error: Audio file not found at {audio_path!s}")
        return

    try:
        print(f"Initializing Whisper pipeline on cuda:{device_id}...")
        # Consider making the pipeline object persistent if processing many files
        asr_pipeline = pipeline(
            "automatic-speech-recognition",
            model=model_name,
            dtype=torch.float16,
            device=f"cuda:{device_id}",
        )

        print(f"Transcribing {audio_path!s}...")
        # Adjust batch_size based on experiments for optimal throughput on H100
        result = asr_pipeline(
            str(audio_path),
            chunk_length_s=30,
            batch_size=16,
            return_timestamps=False,
        )
        transcription = result["text"]  # type:ignore[invalid-argument-type]

        # Save transcription to a text file
        output_txt_path.write_text(transcription, encoding="utf-8")

        print(f"Transcription saved to {output_txt_path!s}")

    except Exception as e:
        print(f"Error transcribing {audio_path!s}: {e}")


# Example usage:
# audio_file = "path/to/output/audio/tiktok_video.mp3"
# output_dir = "path/to/output/transcripts"
# transcribe_audio_whisper(audio_file, output_dir, device_id=0) # Use GPU 0
