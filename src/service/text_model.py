"""Small, versioned CPU model used to exercise the shared serving path."""

from collections import Counter
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math
import re

MODEL_PATH = Path(__file__).parent / "model_artifacts" / "text_topic_v1.json"


class ModelArtifactUnavailable(RuntimeError):
    """The worker could not read its packaged model artifact."""


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


@lru_cache(maxsize=1)
def load_model() -> tuple[dict, str]:
    try:
        payload = MODEL_PATH.read_bytes()
    except OSError as error:
        raise ModelArtifactUnavailable("Packaged text model artifact unavailable") from error
    model = json.loads(payload)
    if model.get("schema_version") != 1 or not model.get("labels"):
        raise ValueError("Invalid text model artifact")
    return model, hashlib.sha256(payload).hexdigest()


def predict(text: str) -> tuple[str, dict[str, float], str]:
    model, revision = load_model()
    words = Counter(tokens(text))
    labels = model["labels"]
    vocabulary_size = len(model["vocabulary"])
    total_documents = sum(model["document_counts"].values())
    log_scores = {}
    for label in labels:
        counts = model["token_counts"][label]
        denominator = sum(counts.values()) + vocabulary_size
        score = math.log(model["document_counts"][label] / total_documents)
        score += sum(count * math.log((counts.get(word, 0) + 1) / denominator)
                     for word, count in words.items() if word in model["vocabulary"])
        log_scores[label] = score
    normalizer = max(log_scores.values())
    weights = {label: math.exp(value - normalizer) for label, value in log_scores.items()}
    total = sum(weights.values())
    scores = {label: weights[label] / total for label in labels}
    return max(labels, key=scores.get), scores, revision
