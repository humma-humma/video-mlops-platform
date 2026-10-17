"""Run isolated baseline and optimization processes, without promoting a candidate."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from scripts.prepare_quality_benchmark import prepare


def memory_state():
    state = {}
    for name in ("memory.events", "memory.current", "memory.max", "memory.peak"):
        path = Path("/sys/fs/cgroup") / name
        if path.is_file():
            state[name] = path.read_text().strip()
    return state


def decoder_preflight(config: Path):
    """Check the installed decoder on the largest full-frame input before VLM load."""
    from torchcodec.decoders import VideoDecoder
    from transformers import AutoProcessor
    cfg = json.loads(config.read_text(encoding="utf-8"))
    manifest = json.loads(Path(cfg["manifest"]).read_text(encoding="utf-8"))
    by_id = {r["video_id"]: r for r in manifest["records"]}
    largest, required = None, -1
    for video_id in cfg["video_ids"]:
        path = Path(cfg["dataset_root"]) / by_id[video_id]["video"]["path"]
        probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,nb_frames", "-of", "json", str(path)], timeout=30))
        stream = probe["streams"][0]
        frame_count = str(stream.get("nb_frames", "0"))
        size = int(stream["width"]) * int(stream["height"]) * (int(frame_count) if frame_count.isdigit() else 0)
        if size > required:
            largest, required = path, size
    processor = AutoProcessor.from_pretrained(cfg["model_name"], revision=cfg["model_revision"], local_files_only=True)
    video_processor = processor.video_processor
    video_processor.num_frames = cfg["max_frames"]
    video_processor.do_sample_frames = True
    frames, metadata = video_processor.fetch_videos(str(largest),
        sample_indices_fn=lambda metadata, **kwargs: video_processor.sample_frames(metadata=metadata, num_frames=cfg["max_frames"]))
    if metadata.video_backend != "torchcodec" or not 0 < len(frames) <= cfg["max_frames"]:
        raise RuntimeError("Processor did not use bounded TorchCodec sampling")
    result = {"decoder": "torchcodec", "video": str(largest), "sampled_frames": len(frames),
              "sampled_bytes": frames.numel() * frames.element_size(), "full_rgb_bytes": required * 3}
    print("PASS bounded decoder preflight: " + json.dumps(result), flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--constrained", action="store_true",
                        help="Compare constrained two-pass generation at four and two frames")
    args = parser.parse_args(argv)
    root = Path("data/outputs/quality-suite") / uuid4().hex
    cache = Path(os.environ.get("HF_HUB_CACHE", "artifacts/benchmark-model-cache")).resolve()
    configs = prepare(cache,
                      root / "configs", Path("data/manifests/development-eval-v1.json"),
                      constrained=args.constrained)
    environment = dict(os.environ, HF_HUB_CACHE=str(cache), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    # Keep the decoder's Torch/CUDA imports out of the orchestrator process.
    subprocess.run([sys.executable, "-c", "from pathlib import Path; from scripts.quality_suite import decoder_preflight; "
        f"decoder_preflight(Path({str(configs[0])!r}))"], check=True, env=environment)
    reports = []
    for config in configs:
        destination = root / config.stem
        before = memory_state()
        try:
            subprocess.run([sys.executable, "-m", "scripts.run_experiment", "--config", str(config),
                            "--set", "output=" + json.dumps(str(destination))], check=True, env=environment)
        except subprocess.CalledProcessError as error:
            failure = {"experiment": config.stem, "returncode": error.returncode,
                       "memory_before": before, "memory_after": memory_state(),
                       "note": "Negative return codes are Unix signals; compare memory.events oom_kill to confirm cgroup OOM."}
            (root / "failure.json").write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
            print(f"Benchmark failed; diagnostics saved to {root / 'failure.json'}", flush=True)
            raise
        paths = list(destination.glob("*/report.json"))
        if len(paths) != 1:
            raise RuntimeError("Expected exactly one isolated experiment report")
        report = json.loads(paths[0].read_text(encoding="utf-8"))
        if report["quality_status"] != "complete":
            raise RuntimeError(f"Incomplete quality measurements: {paths[0]}")
        reports.append({"name": report["name"], "report": str(paths[0]), "metrics": report["metrics"],
                        "sample_count": report["sample_count"], "sample_hash": report["lineage"]["sample_hash"]})
    (root / "comparison.json").write_text(json.dumps({"purpose": "development comparison; human quality review still required",
        "reports": reports, "category_constraints": args.constrained,
        "promoted": False}, indent=2) + "\n", encoding="utf-8")
    print(f"PASS measured development comparison: {root / 'comparison.json'}")


if __name__ == "__main__":
    main()
