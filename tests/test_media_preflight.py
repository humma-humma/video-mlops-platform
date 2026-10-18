"""Frame-decode failures must be typed without leaking decoder output."""

from pathlib import Path
import subprocess
from unittest.mock import Mock, patch

import pytest

from src.service.deployments import VideoAdapter
from src.service.lifecycle import classify_failure
from src.service.media import (VideoDecodeFailure, VideoDecodeTimeout,
                               VideoDecoderUnavailable, check_first_frame)


def test_first_frame_preflight_distinguishes_failure_and_timeout():
    with patch("src.service.media.subprocess.run", return_value=Mock(returncode=0)) as run:
        check_first_frame(Path("sample.mp4"))
    assert run.call_args.args[0][-7:] == ["-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"]
    with patch("src.service.media.subprocess.run", return_value=Mock(returncode=1)):
        with pytest.raises(VideoDecodeFailure):
            check_first_frame(Path("sample.mp4"))
    with patch("src.service.media.subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 15)):
        with pytest.raises(VideoDecodeTimeout):
            check_first_frame(Path("sample.mp4"))
    with patch("src.service.media.subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(VideoDecoderUnavailable):
            check_first_frame(Path("sample.mp4"))


def test_decode_failure_precedes_model_load_and_has_stable_code():
    with patch("src.service.media.check_first_frame", side_effect=VideoDecodeFailure()), patch(
            "src.service.inference.get_model_runner") as model:
        with pytest.raises(VideoDecodeFailure):
            VideoAdapter().run(Path("sample.mp4"), {})
    model.assert_not_called()
    assert classify_failure(VideoDecodeFailure()) == ("decode_failed", "Video frame preflight failed")
    assert classify_failure(VideoDecodeTimeout())[0] == "decode_timeout"
    assert classify_failure(VideoDecoderUnavailable())[0] == "decoder_unavailable"
