from pathlib import Path

from .extract_audio import extract_audio_mp3, transcribe_audio_whisper


def get_audio_transcript(
    video_id: str,
    video_path: Path,
    audio_folder: Path,
    transcript_folder: Path,
) -> str:
    """Extract or load audio transcript for a given video."""
    transcript_path = transcript_folder / f"{video_id}.txt"

    if transcript_path.exists():
        return transcript_path.read_text(encoding="utf-8").strip()

    try:
        extract_audio_mp3(video_path, video_id, audio_folder)
        audio_path = audio_folder / f"{video_id}.mp3"
        transcribe_audio_whisper(audio_path, video_id, transcript_folder, device_id=0)
        return transcript_path.read_text(encoding="utf-8").strip()
    except Exception as e:
        print(f"⚠️ Error processing audio for {video_id}: {e}")
        return ""
