import time

import torch
from transformers import ImageTextToTextPipeline, pipeline


def load_model(model_name: str) -> tuple[ImageTextToTextPipeline, float]:
    """Load processor and model with timing info."""
    start_time = time.perf_counter()
    pipe = pipeline(
        "image-text-to-text",
        model=model_name,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    load_time = time.perf_counter() - start_time
    print(f"✅ Model loaded in {load_time:.2f}s")
    return pipe, load_time
