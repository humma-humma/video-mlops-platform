import time

import torch
from transformers import (
    AutoModelForImageTextToText,
    AutoProcessor,
)


def load_model(model_name: str, device: str):
    """Load processor and model with timing info."""
    start_time = time.perf_counter()
    processor = AutoProcessor.from_pretrained(model_name)
    model = AutoModelForImageTextToText.from_pretrained(
        model_name,
        dtype=torch.bfloat16,
    ).to(device)  # type:ignore[invalid-argument-type]
    load_time = time.perf_counter() - start_time
    print(f"✅ Model loaded in {load_time:.2f}s")
    return processor, model, load_time
