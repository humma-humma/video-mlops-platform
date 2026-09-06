import time

import torch
from transformers import BaseVideoProcessor, ImageTextToTextPipeline, pipeline

from src.config import InferenceConfig


def load_model(cfg: InferenceConfig) -> tuple[ImageTextToTextPipeline, float]:
    """Load processor and model with timing info."""
    start_time = time.perf_counter()
    if cfg.model_dtype == "float16":
        dtype = torch.float16
    elif cfg.model_dtype == "bfloat16":
        dtype = torch.bfloat16
    else:
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    pipe = pipeline(
        "image-text-to-text",
        model=cfg.model_name,
        device_map="auto",
        dtype=dtype,
        use_cache=cfg.use_kv_cache,
        model_kwargs={"_attn_implementation": cfg.attention_implementation}
        if cfg.attention_implementation
        else {},
        batch_size=cfg.batch_size,
        num_workers=cfg.num_workers,
    )

    if cfg.max_frames is not None:
        processor = pipe.processor
        if processor is not None:
            video_processor = getattr(processor, "video_processor", None)
            if isinstance(video_processor, BaseVideoProcessor):
                print(f"🚀 Setting max frames to {cfg.max_frames}...")
                video_processor.num_frames = cfg.max_frames  # type: ignore[reportAttributeAccessIssue]

    if cfg.torch_compile:
        print("🚀 Compiling model...")
        # Copied the options from unsloth training repo
        unsloth_torch_compile_options = {
            "epilogue_fusion": True,
            "max_autotune": True,
            "shape_padding": True,
            "triton.cudagraphs": False,
        }
        pipe.model.compile(
            fullgraph=False,
            dynamic=True,
            options=unsloth_torch_compile_options,
        )

    load_time = time.perf_counter() - start_time
    print(f"✅ Model loaded in {load_time:.2f}s")
    return pipe, load_time
