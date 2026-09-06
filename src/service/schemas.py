from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    job_id: str
    status: Literal["PENDING", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED"]
    result: dict | None = None
    error: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None


class HealthResponse(BaseModel):
    status: str
    database: str
    queue: str


class SubmissionResponse(BaseModel):
    job_id: str
    status: str
