import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from fastapi import HTTPException
from starlette.responses import JSONResponse

from .config import settings

class UploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = settings.max_upload_bytes + 4 * settings.max_transcript_chars + 65536
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        if length and (not length.isdigit() or int(length) > limit):
            return await JSONResponse({"detail": "Request body exceeds upload limit"}, status_code=413)(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise HTTPException(413, "Request body exceeds upload limit")
            return message

        await self.app(scope, limited_receive, send)

def validate_probe(probe):
    streams = probe.get("streams", [])
    if not any(s.get("codec_type") == "video" for s in streams):
        raise ValueError("Upload contains no video stream")
    try:
        duration = float(probe["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Video duration is unavailable") from None
    import math
    if not math.isfinite(duration) or duration <= 0 or duration > settings.max_video_duration_seconds:
        raise ValueError("Video duration exceeds the allowed range")

def validate_video(data: bytes, suffix: str):
    with TemporaryDirectory() as directory:
        path = Path(directory) / ("upload" + suffix)
        path.write_bytes(data)
        try:
            result = subprocess.run([
                "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
                "-show_format", "-show_streams", "-of", "json", str(path),
            ], capture_output=True, timeout=settings.ffprobe_timeout_seconds, check=True)
            validate_probe(json.loads(result.stdout))
        except subprocess.TimeoutExpired:
            raise ValueError("Video inspection timed out") from None
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            raise ValueError("Upload is not a readable video") from None
