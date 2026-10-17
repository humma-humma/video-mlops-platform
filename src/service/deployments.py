"""Code-reviewed deployment adapters; no user-supplied model code is executed."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import time

from .schemas import InferenceResult, TextTopicResult


class ModelAdapter(Protocol):
    deployment_id: str
    input_kind: str
    resource: str
    queue: str

    def describe(self) -> dict: ...
    def run(self, input_path: Path, metadata: dict) -> dict: ...
    def validate_result(self, result: dict) -> dict: ...


@dataclass(frozen=True)
class VideoAdapter:
    deployment_id: str = "video-summary-v1"
    input_kind: str = "video"
    resource: str = "gpu"
    queue: str = "video-inference"

    def describe(self) -> dict:
        from .config import settings
        return {"model_version": settings.model_name, "model_revision": settings.model_revision}

    def run(self, input_path: Path, metadata: dict) -> dict:
        from .inference import get_model_runner
        return get_model_runner().run(input_path, metadata.get("transcript", ""))

    def validate_result(self, result: dict) -> dict:
        return InferenceResult.model_validate(result).model_dump()


@dataclass(frozen=True)
class TextTopicAdapter:
    deployment_id: str = "text-topic-v1"
    input_kind: str = "text"
    resource: str = "cpu"
    queue: str = "cpu-inference"

    def describe(self) -> dict:
        from .text_model import load_model
        return {"model_version": "toy-text-topic-naive-bayes-v1",
                "model_revision": load_model()[1]}

    def run(self, input_path: Path, metadata: dict) -> dict:
        from .text_model import predict
        start = time.perf_counter()
        label, scores, revision = predict(input_path.read_text(encoding="utf-8"))
        return {"schema_version": "1", "deployment_id": self.deployment_id,
                "model_version": "toy-text-topic-naive-bayes-v1", "model_revision": revision,
                "output": {"label": label, "scores": scores},
                "timings": {"inference_total": time.perf_counter() - start}}

    def validate_result(self, result: dict) -> dict:
        return TextTopicResult.model_validate(result).model_dump()


DEPLOYMENTS: dict[str, ModelAdapter] = {
    adapter.deployment_id: adapter for adapter in (VideoAdapter(), TextTopicAdapter())
}


def get_deployment(deployment_id: str) -> ModelAdapter:
    return DEPLOYMENTS[deployment_id]
