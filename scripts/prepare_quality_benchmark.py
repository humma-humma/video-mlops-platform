"""Download pinned public checkpoints and resolve comparable experiments."""
import argparse
import json
from pathlib import Path

from src.experiments import ExperimentConfig
from src.lineage import canonical_hash, sha256_file

MODEL = "HuggingFaceTB/SmolVLM2-2.2B-Instruct"
MODEL_REVISION = "482adb537c021c86670beed01cd58990d01e72e4"
METRIC = "FacebookAI/xlm-roberta-large"
METRIC_REVISION = "c23d21b0620b635a76227c604d44e43a9f0ee389"


def prepare(cache: Path, output: Path, subset_path: Path, *, download=True, constrained=False):
    subset = json.loads(subset_path.read_text(encoding="utf-8"))
    manifest = Path("data/manifests/tiktok-video-v1.json")
    if subset["manifest_hash"] != sha256_file(manifest):
        raise ValueError("Subset refers to a different dataset manifest")
    if subset["sample_hash"] != canonical_hash(sorted(record["video_id"] for record in subset["records"])):
        raise ValueError("Subset video IDs differ from the recorded sample hash")
    metric_snapshot = cache.resolve() / ("models--" + METRIC.replace("/", "--")) / "snapshots" / METRIC_REVISION
    if download:
        from huggingface_hub import snapshot_download
        for model, revision in ((MODEL, MODEL_REVISION), (METRIC, METRIC_REVISION)):
            path = snapshot_download(model, revision=revision, cache_dir=str(cache),
                allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model"])
            if Path(path).name != revision:
                raise RuntimeError("Downloaded checkpoint differs from pinned revision")
    output.mkdir(parents=True, exist_ok=True)
    configs = []
    variants = (("baseline", 4, "per_video_two_pass"),
                ("fewer-frames", 2, "per_video_two_pass"),
                ("combined", 4, "per_video_combined"))
    if constrained:
        variants = (("constrained-baseline", 4, "per_video_two_pass"),
                    ("constrained-fewer-frames", 2, "per_video_two_pass"))
    for name, frames, strategy in variants:
        cfg = ExperimentConfig(name=f"development-2.2b-{name}", model_name=MODEL, model_revision=MODEL_REVISION,
            video_ids=[record["video_id"] for record in subset["records"]], max_frames=frames,
            strategy=strategy, evaluate_summary=True, summary_metric_snapshot=metric_snapshot,
            summary_metric_layers=17, constrain_category=constrained)
        path = output / f"{name}.json"
        path.write_text(cfg.model_dump_json(indent=2) + "\n", encoding="utf-8")
        configs.append(path)
    return configs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=Path("artifacts/benchmark-model-cache"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/outputs/quality-configs"))
    parser.add_argument("--subset", type=Path, default=Path("data/manifests/development-eval-v1.json"))
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--constrained", action="store_true")
    args = parser.parse_args()
    for path in prepare(args.cache_dir, args.output_dir, args.subset, download=not args.skip_download,
                        constrained=args.constrained):
        print(path)


if __name__ == "__main__":
    main()
