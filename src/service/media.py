"""Bounded video-frame preflight before allocating the GPU model."""

from pathlib import Path
import subprocess


class VideoDecodeFailure(Exception):
    """A local decoder could not produce the first video frame."""


class VideoDecodeTimeout(Exception):
    """Frame preflight exceeded its time budget; input validity is unknown."""


class VideoDecoderUnavailable(Exception):
    """The local decoder executable could not be started."""


def check_first_frame(path: Path, timeout_seconds: int = 15) -> None:
    command = ["ffmpeg", "-v", "error", "-xerror", "-nostdin",
               "-protocol_whitelist", "file,pipe", "-i", str(path),
               "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"]
    try:
        result = subprocess.run(command, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        raise VideoDecodeTimeout("Video frame preflight timed out") from None
    except OSError:
        raise VideoDecoderUnavailable("Video decoder is unavailable") from None
    if result.returncode:
        raise VideoDecodeFailure("Video frame preflight failed")
