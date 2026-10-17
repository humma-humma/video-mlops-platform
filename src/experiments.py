"""Strict experiment configuration and fail-closed candidate comparisons."""
import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal

from src.lineage import canonical_hash


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    manifest: Path = Path("data/manifests/tiktok-video-v1.json")
    dataset_root: Path = Path("data/inputs")
    video_ids: list[str] = Field(min_length=1)
    max_frames: int = Field(default=4, ge=1)
    strategy: Literal["per_video_two_pass", "per_video_combined"] = "per_video_two_pass"
    evaluate_summary: bool = True
    constrain_category: bool = False
    summary_metric_snapshot: Path | None = None
    summary_metric_layers: int | None = Field(default=None, ge=1)
    output: Path = Path("data/outputs/experiments")

    @model_validator(mode="after")
    def validate_category_constraint(self):
        if self.constrain_category and self.strategy != "per_video_two_pass":
            raise ValueError("Category constraints require the two-pass strategy")
        return self

    @field_validator("video_ids")
    @classmethod
    def unique_ids(cls, value):
        if len(value) != len(set(value)) or any(not item.strip() for item in value):
            raise ValueError("Video IDs must be nonempty and unique")
        return sorted(value)


class GatePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_by: str = Field(min_length=1)
    minimum_samples: int = Field(ge=2)
    minimum_category_samples: int = Field(ge=2)
    max_bertscore_drop: float = Field(ge=0, le=1)
    max_accuracy_drop: float = Field(ge=0, le=1)
    max_error_rate: float = Field(ge=0, le=1)
    max_latency_ratio: float = Field(gt=0)
    max_gpu_memory_ratio: float = Field(gt=0)


def evaluate_gate(candidate: dict, baseline: dict, policy: GatePolicy) -> dict:
    """Never infer approval or thresholds from a candidate's own measurements."""
    reasons = []
    if canonical_hash(baseline) != policy.baseline_hash:
        reasons.append("Baseline content differs from the reviewed policy")
    required_lineage = ("model_revision", "processor_revision", "manifest_hash", "code_hash",
                        "prompt_hash", "taxonomy_hash", "inference_config_hash", "sample_hash")
    for label, report in (("baseline", baseline), ("candidate", candidate)):
        lineage = report.get("lineage", {})
        for key in required_lineage:
            if not lineage.get(key):
                reasons.append(f"{label}: missing lineage {key}")
            else:
                import re
                size = 40 if key in ("model_revision", "processor_revision") else 64
                if not re.fullmatch(rf"[0-9a-f]{{{size}}}", str(lineage[key])):
                    reasons.append(f"{label}: invalid lineage digest {key}")
        if report.get("purpose") != "candidate_evaluation":
            reasons.append(f"{label}: smoke results cannot qualify for promotion")
        if report.get("sample_count", 0) < policy.minimum_samples:
            reasons.append(f"{label}: insufficient evaluation samples")
        if report.get("category_evaluated_count", 0) < policy.minimum_category_samples:
            reasons.append(f"{label}: insufficient category evaluation coverage")
        if report.get("quality_status") != "complete":
            reasons.append(f"{label}: summary/category evaluation is incomplete")
        for key in ("gpu", "torch", "transformers"):
            if not report.get("environment", {}).get(key):
                reasons.append(f"{label}: missing runtime {key}")
    for key in ("manifest_hash", "sample_hash", "taxonomy_hash"):
        if candidate.get("lineage", {}).get(key) != baseline.get("lineage", {}).get(key):
            reasons.append(f"Incomparable evaluation inputs: {key}")
    if candidate.get("environment") != baseline.get("environment"):
        reasons.append("Performance runtime/hardware differs from baseline")
    import re
    if not re.fullmatch(r"[0-9a-f]{64}", str(candidate.get("summary_metric_hash", ""))) or candidate.get("summary_metric_hash") != baseline.get("summary_metric_hash"):
        reasons.append("Summary metric model/version is unpinned or differs")
    required_metrics = ("bertscore_f1", "category_accuracy", "error_rate", "latency_p95_seconds", "peak_gpu_memory_bytes")
    metrics_valid = True
    for label, report in (("baseline", baseline), ("candidate", candidate)):
        for key in required_metrics:
            value = report.get("metrics", {}).get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                reasons.append(f"{label}: missing/invalid metric {key}")
                metrics_valid = False
            elif key in ("bertscore_f1", "category_accuracy", "error_rate") and value > 1:
                reasons.append(f"{label}: out-of-range metric {key}")
                metrics_valid = False
    if metrics_valid:
        c, b = candidate["metrics"], baseline["metrics"]
        comparisons = [
            (c["bertscore_f1"] >= b["bertscore_f1"] - policy.max_bertscore_drop, "Summary quality regressed"),
            (c["category_accuracy"] >= b["category_accuracy"] - policy.max_accuracy_drop, "Category accuracy regressed"),
            (c["error_rate"] <= policy.max_error_rate, "Error rate exceeds policy"),
            (c["latency_p95_seconds"] <= b["latency_p95_seconds"] * policy.max_latency_ratio, "P95 latency regressed"),
            (c["peak_gpu_memory_bytes"] <= b["peak_gpu_memory_bytes"] * policy.max_gpu_memory_ratio, "GPU memory regressed"),
        ]
        reasons.extend(message for passed, message in comparisons if not passed)
    return {"schema_version": "1", "passed": not reasons, "reasons": reasons,
            "candidate_hash": canonical_hash(candidate), "baseline_hash": canonical_hash(baseline),
            "policy_hash": canonical_hash(policy.model_dump()), "reviewed_by": policy.reviewed_by}
