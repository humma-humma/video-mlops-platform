from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.category_utils import is_canonical_category


class JobResponse(BaseModel):
    job_id: str
    deployment_id: str = "video-summary-v1"
    status: Literal["PENDING", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
    result: dict | None = None
    error: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None


class HealthResponse(BaseModel):
    status: str
    database: str
    queue: str
    storage: str


class SubmissionResponse(BaseModel):
    job_id: str
    status: str

class InferenceResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: Literal["1"]
    video_id: str
    summary: str = Field(min_length=1)
    category: str
    model_version: str = Field(min_length=1)
    timings: dict[str, float]

    @field_validator("summary")
    @classmethod
    def nonempty_summary(cls, value):
        if not value.strip():
            raise ValueError("Empty summary")
        return value

    @field_validator("category")
    @classmethod
    def canonical_category(cls, value):
        if not is_canonical_category(value):
            raise ValueError("Category outside taxonomy")
        return value

    @field_validator("timings")
    @classmethod
    def valid_timings(cls, value):
        import math
        if any(not math.isfinite(n) or n < 0 for n in value.values()):
            raise ValueError("Timings must be finite and nonnegative")
        return value


class TextTopicResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: Literal["1"]
    deployment_id: Literal["text-topic-v1"]
    model_version: str = Field(min_length=1)
    model_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    output: dict
    timings: dict[str, float]

    @field_validator("output")
    @classmethod
    def valid_output(cls, value):
        import math
        from .text_model import load_model
        labels = set(load_model()[0]["labels"])
        scores = value.get("scores")
        if (value.get("label") not in labels or not isinstance(scores, dict)
                or set(scores) != labels or any(not isinstance(score, (int, float))
                or not math.isfinite(score) or score < 0 or score > 1 for score in scores.values())
                or abs(sum(scores.values()) - 1) > 1e-6):
            raise ValueError("Invalid text model output")
        return value

    @field_validator("timings")
    @classmethod
    def valid_timings(cls, value):
        import math
        if any(not math.isfinite(n) or n < 0 for n in value.values()):
            raise ValueError("Timings must be finite and nonnegative")
        return value
