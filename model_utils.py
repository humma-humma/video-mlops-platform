import torch
import time
from transformers import AutoProcessor, AutoModelForImageTextToText

def load_model(model_name: str, device: str):
    """Load processor and model with timing info."""
    start_time = time.time()
    processor = AutoProcessor.from_pretrained(model_name)
    model = AutoModelForImageTextToText.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16
    ).to(device)
    load_time = time.time() - start_time
    print(f"✅ Model loaded in {load_time:.2f}s")
    return processor, model, load_time
