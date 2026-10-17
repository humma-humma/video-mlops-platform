import pytest
from pydantic import ValidationError

from src.service.config import Settings


def test_empty_compose_api_key_is_unset():
    assert Settings(api_key="").api_key is None


@pytest.mark.parametrize("overrides", [
    {"environment": "staging"},
    {"environment": "production", "api_key": "short", "use_fake_inference": False},
    {"environment": "staging", "api_key": "x" * 32},
    {"task_soft_time_limit": 100, "task_time_limit": 100},
    {"max_outstanding_jobs": 0},
    {"release_id": "invalid id"},
])
def test_unsafe_deployment_settings_are_refused(overrides):
    with pytest.raises(ValidationError):
        Settings(**overrides)


def test_authenticated_real_staging_configuration():
    assert Settings(environment="staging", api_key="x" * 32, use_fake_inference=False).environment == "staging"
