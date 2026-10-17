from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from pydantic import Field, SecretStr, field_validator, model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIDEO_", extra="ignore")
    database_url: str = "postgresql+psycopg://video:video@localhost:5432/video"
    broker_url: str = "redis://localhost:6379/0"
    artifact_root: str = "./artifacts"
    artifact_backend: Literal["filesystem", "s3"] = "filesystem"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "video-artifacts"
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    model_name: str = "HuggingFaceTB/SmolVLM2-500M-Video-Instruct"
    model_revision: str = "7b375e1b73b11138ff12fe22c8f2822d8fe03467"
    max_frames: int = 4
    worker_scratch_root: str = "./worker-scratch"
    max_transcript_chars: int = 100_000
    max_upload_bytes: int = 500 * 1024 * 1024
    use_fake_inference: bool = True
    api_key: SecretStr | None = None
    environment: Literal["local", "staging", "production"] = "local"
    release_id: str = Field(default="local-unversioned", pattern=r"^[a-zA-Z0-9._-]{1,64}$")
    max_job_attempts: int = Field(default=3, ge=1)
    retry_backoff_seconds: int = Field(default=15, ge=1)
    task_soft_time_limit: int = Field(default=840, ge=1)
    task_time_limit: int = Field(default=900, ge=2)
    task_queue: str = "video-inference"
    dispatch_interval_seconds: int = Field(default=10, ge=1)
    redispatch_after_seconds: int = Field(default=120, ge=10)
    request_rate_limit_per_minute: int = Field(default=600, ge=0)
    max_outstanding_jobs: int = Field(default=2, ge=1)
    validate_media: bool = True
    max_video_duration_seconds: float = Field(default=600, gt=0)
    ffprobe_timeout_seconds: int = Field(default=15, ge=1)

    @field_validator("api_key", mode="before")
    @classmethod
    def empty_key_is_unset(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_deployment(self):
        if self.task_soft_time_limit >= self.task_time_limit:
            raise ValueError("Soft task limit must be lower than the hard limit")
        if self.environment != "local" and (not self.api_key or len(self.api_key.get_secret_value()) < 32):
            raise ValueError("Non-local deployments require an API key of at least 32 characters")
        if self.environment != "local" and self.use_fake_inference:
            raise ValueError("Non-local deployments must disable fake inference")
        return self


settings = Settings()
