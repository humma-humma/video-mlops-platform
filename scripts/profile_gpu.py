"""Profile one cached local sample directly, without submitting an API job."""
import argparse
import gzip
import hashlib
import json
import os
import platform
import shutil
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from src.service.gpu_metrics import gpu_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/outputs/gpu-profile"))
    args = parser.parse_args()
    for path in (args.video, args.transcript):
        if not path.is_file():
            parser.error(f"Missing input: {path}")
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    import transformers
    from src.config import InferenceConfig
    from src.inference_utils import create_messages, run_inference
    from src.model_utils import load_model

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required")
    # GET only, for evidence that the profiler does not enqueue jobs.
    opener = build_opener(ProxyHandler({}))
    def job_ids():
        from urllib.request import Request
        headers = {"X-API-Key": os.environ["VIDEO_API_KEY"]} if os.environ.get("VIDEO_API_KEY") else {}
        with opener.open(Request("http://127.0.0.1:8000/api/v1/jobs?limit=100", headers=headers), timeout=10) as response:
            body = json.load(response)
        jobs = body.get("jobs", []) if isinstance(body, dict) else body
        if any(job["status"] in {"RUNNING", "QUEUED"} for job in jobs):
            raise RuntimeError("Service has active jobs; retry after the queue drains")
        return sorted(job.get("job_id", job.get("id")) for job in jobs)

    before = job_ids()
    samples = [gpu_snapshot()]
    stop = threading.Event()
    def sample():
        while not stop.wait(1):
            samples.append(gpu_snapshot())
    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    cfg = InferenceConfig(video_folder=args.video.parent, audio_folder=Path("data/inputs/audios"),
        audio_transcript_folder=args.transcript.parent, ground_truth_file=Path("data/inputs/ground_truth.csv"),
        model_name="HuggingFaceTB/SmolVLM2-500M-Video-Instruct",
        model_revision="7b375e1b73b11138ff12fe22c8f2822d8fe03467", max_frames=4,
        use_kv_cache=True, model_dtype="auto", csv_folder=args.output, statistics_folder=args.output,
        file_name="profile")
    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "config": asdict(cfg),
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "torch": torch.__version__, "transformers": transformers.__version__},
        "input_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.video, args.transcript)},
        "scope": "native local cached sample; no API submission; not rebuilt Docker acceptance or a capacity test",
        "limitations": ["Device-wide GPU samples include other applications", "Profiler adds overhead",
                        "Single sample, single warmup, one measured two-pass run", "torchvision fallback may decode the entire clip"],
        "profiler_configuration": {"activities": ["CPU", "CUDA"], "profile_memory": False},
        "job_ids_before": before, "stages_seconds": {}}
    try:
        pipe, load_seconds = load_model(cfg)
        torch.cuda.synchronize()
        report["model_load_seconds"] = load_seconds
        report["model_revision"] = getattr(pipe.model.config, "_commit_hash", None)
        messages = {mode: [create_messages(args.video, args.transcript.read_text(encoding="utf-8"), mode=mode)] for mode in ("summary", "category")}
        start = time.perf_counter()
        for mode in messages:
            run_inference(pipe, messages[mode], mode=mode, constrain_category=mode == "category")
        torch.cuda.synchronize()
        report["warmup_seconds"] = time.perf_counter() - start
        torch.cuda.reset_peak_memory_stats()
        with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA],
                                    profile_memory=False) as profile:
            for mode in messages:
                torch.cuda.synchronize()
                start = time.perf_counter()
                with torch.profiler.record_function(f"video_{mode}"):
                    run_inference(pipe, messages[mode], mode=mode, constrain_category=mode == "category")
                    torch.cuda.synchronize()
                report["stages_seconds"][mode] = time.perf_counter() - start
        report["peak_process_allocated_bytes"] = torch.cuda.max_memory_allocated()
        report["peak_process_reserved_bytes"] = torch.cuda.max_memory_reserved()
        profile.export_chrome_trace(str(args.output / "trace.json"))
        with (args.output / "trace.json").open("rb") as source, gzip.open(args.output / "trace.json.gz", "wb", compresslevel=1) as dest:
            shutil.copyfileobj(source, dest, 1024 * 1024)
        averages = profile.key_averages()
        (args.output / "operators.txt").write_text(averages.table(sort_by="self_device_time_total", row_limit=25), encoding="utf-8")
        report["cuda_device_event_count"] = sum(1 for event in profile.events() if event.device_type == torch.autograd.DeviceType.CUDA)
        report["job_ids_after"] = job_ids()
        report["job_set_unchanged"] = before == report["job_ids_after"]
        report["status"] = "completed"
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        stop.set()
        thread.join(timeout=7)
        report["gpu_samples"] = samples
        report["baseline_gpu"] = samples[0]
        (args.output / "report.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"Profile evidence: {args.output / 'report.json'}")


if __name__ == "__main__":
    main()
