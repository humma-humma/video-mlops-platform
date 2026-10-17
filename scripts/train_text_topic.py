"""Rebuild the tiny illustrative CPU model artifact without external downloads."""

from collections import Counter
from pathlib import Path
import json

from src.service.text_model import MODEL_PATH, tokens

EXAMPLES = {
    "cooking": [
        "Bake bread in the oven with flour and yeast",
        "Chop vegetables and simmer the soup",
        "Cook pasta with tomato sauce and herbs",
        "Whisk eggs and butter for the cake",
        "Roast garlic and potatoes for dinner",
        "Prepare a recipe with rice and spices",
    ],
    "sports": [
        "The football team scored a goal in the match",
        "The athlete trained for the marathon race",
        "The basketball player won the game",
        "The coach planned a defensive strategy for the tournament",
        "The tennis match ended after three sets",
        "The runner sprinted to win the championship",
    ],
    "technology": [
        "The software developer fixed a computer bug",
        "The server runs a database and an API",
        "The engineer deployed a machine learning model",
        "The laptop processor uses memory and storage",
        "The application uses Python code and a network",
        "The GPU accelerates inference for the model",
    ],
}


def build_model() -> dict:
    labels = sorted(EXAMPLES)
    counts = {label: Counter(word for text in EXAMPLES[label] for word in tokens(text))
              for label in labels}
    return {"schema_version": 1, "training_set": "illustrative-18-documents-v1",
            "labels": labels, "document_counts": {label: len(EXAMPLES[label]) for label in labels},
            "vocabulary": sorted(set().union(*(counts[label] for label in labels))),
            "token_counts": {label: dict(sorted(counts[label].items())) for label in labels}}


if __name__ == "__main__":
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_bytes((json.dumps(build_model(), indent=2) + "\n").encode("utf-8"))
    print(MODEL_PATH)
