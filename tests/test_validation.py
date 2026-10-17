import pytest

from src.service.validation import validate_probe

def test_probe_accepts_video_with_valid_duration():
    validate_probe({"streams": [{"codec_type": "video"}], "format": {"duration": "5.25"}})

@pytest.mark.parametrize("probe", [
    {"streams": [{"codec_type": "audio"}], "format": {"duration": "5"}},
    {"streams": [{"codec_type": "video"}], "format": {"duration": "nan"}},
    {"streams": [{"codec_type": "video"}], "format": {"duration": "999999"}},
    {"streams": [{"codec_type": "video"}], "format": {}},
])
def test_probe_rejects_invalid_media(probe):
    with pytest.raises(ValueError):
        validate_probe(probe)
