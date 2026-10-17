from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.category_utils import is_canonical_category


class JobResponse(BaseModel):
    job_id: str
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
