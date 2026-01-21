import os
from utils.extract_audio import extract_audio_mp3, transcribe_audio_whisper

def get_audio_transcript(video_id: str, video_path: str, audio_folder: str, transcript_folder: str) -> str:
    """Extract or load audio transcript for a given video."""
    transcript_path = os.path.join(transcript_folder, f"{video_id}.txt")

    if os.path.exists(transcript_path):
        with open(transcript_path, 'r', encoding='utf-8') as f:
            return f.read().strip()

    try:
        extract_audio_mp3(video_path, audio_folder)
        audio_path = os.path.join(audio_folder, f"{video_id}.mp3")
        transcribe_audio_whisper(audio_path, video_id, transcript_folder, device_id=0)
        with open(transcript_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        print(f"⚠️ Error processing audio for {video_id}: {e}")
        return ""
