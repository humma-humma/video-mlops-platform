from moviepy import VideoFileClip
import os
import sys

def extract_audio_mp3(video_path, video_id, output_folder):
    """
    Extracts audio from a video file and saves it as an MP3 using MoviePy.

    Args:
        video_path (str): Path to the input video file.
        output_folder (str): Folder to save the extracted MP3 audio file.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    try:
        video_clip = VideoFileClip(video_path)
        
        # Check if the video has an audio track
        if video_clip.audio is None:
            print(f"Warning: Video {video_path} has no audio track. Skipping audio extraction.")
            video_clip.close() # Close the video clip object
            return

        # Construct output path
        base_filename = video_id#os.path.splitext(os.path.basename(video_path))
        output_audio_path = os.path.join(output_folder, f"{base_filename}.mp3")

        # Extract and write the audio file
        # codec='mp3' is often implicit with.mp3 extension but can be specified
        # bitrate='192k' or similar can be added for quality control if needed
        video_clip.audio.write_audiofile(output_audio_path, codec='mp3') 
        
        # Close the clips to release resources
        video_clip.audio.close()
        video_clip.close()
        
        print(f"Successfully extracted audio to {output_audio_path}")

    except Exception as e:
        print(f"Error extracting audio from {video_path}: {e}")
        # Ensure clip is closed even if error occurs during write
        if 'video_clip' in locals() and video_clip:
             if video_clip.audio: video_clip.audio.close()
             video_clip.close()

# Optional: Use this function to extract audio from a video file
# Example usage:
# video_file = "path/to/your/tiktok_video.mp4"
# output_dir = "path/to/output/audio"
# extract_audio_mp3(video_file, output_dir)

from transformers import pipeline
import torch
import os

def transcribe_audio_whisper(audio_path, video_id, output_folder, model_name="openai/whisper-large-v3", device_id=0):
    """
    Transcribes an audio file using the Whisper model via Hugging Face pipeline.

    Args:
        audio_path (str): Path to the input audio file (e.g., MP3, WAV).
        output_folder (str): Folder to save the transcription text file.
        model_name (str): The Whisper model checkpoint name.
        device_id (int): The GPU device ID to use.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        
    if not os.path.exists(audio_path):
        print(f"Error: Audio file not found at {audio_path}")
        return

    try:
        print(f"Initializing Whisper pipeline on cuda:{device_id}...")
        # Consider making the pipeline object persistent if processing many files
        asr_pipeline = pipeline(
            "automatic-speech-recognition",
            model=model_name,
            torch_dtype=torch.float16,
            device=f"cuda:{device_id}"
        )
        
        print(f"Transcribing {audio_path}...")
        # Adjust batch_size based on experiments for optimal throughput on H100
        result = asr_pipeline(audio_path, chunk_length_s=30, batch_size=16, return_timestamps=False) 
        transcription = result["text"]

        # Save transcription to a text file
        base_filename = video_id#os.path.splitext(os.path.basename(audio_path))
        output_txt_path = os.path.join(output_folder, f"{base_filename}.txt")
        
        with open(output_txt_path, 'w', encoding='utf-8') as f:
            f.write(transcription)
            
        print(f"Transcription saved to {output_txt_path}")

    except Exception as e:
        print(f"Error transcribing {audio_path}: {e}")

# Example usage:
# audio_file = "path/to/output/audio/tiktok_video.mp3"
# output_dir = "path/to/output/transcripts"
# transcribe_audio_whisper(audio_file, output_dir, device_id=0) # Use GPU 0