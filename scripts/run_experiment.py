"""Run a pinned GPU experiment, preserving immutable reports and input lineage."""
import argparse
import csv
from dataclasses import asdict
from importlib.metadata import version
import json
import os
from pathlib import Path
import statistics
import time
from uuid import uuid4

from src.experiments import ExperimentConfig
from src.lineage import canonical_hash, sha256_file, source_lineage, verify_manifest


def run_recorded_inference(prepared, inference, strategy, journal: Path):
    """Keep completed per-video evidence even if a later process is killed."""
    from src.pipeline import BatchPredictions, run_isolated_inference
    predictions, failures = [], []
    summary = category = combined = 0.0
    with journal.open("x", encoding="utf-8") as stream:
        for number, video in enumerate(prepared, 1):
            print(f"Inference {number}/{len(prepared)} video={video.video_id}", flush=True)
            def recorded(messages, mode):
                outputs, seconds = inference(messages, mode)
                stream.write(json.dumps({"record_type": "generation", "video_id": video.video_id,
                    "stage": mode, "outputs": outputs, "seconds": seconds}, allow_nan=False) + "\n")
                stream.flush()
                return outputs, seconds
            result = run_isolated_inference([video], recorded, strategy)
            predictions.extend(result.predictions)
            failures.extend(result.failures)
            summary += result.summary_time
            category += result.category_time
            combined += result.combined_time
            stream.write(json.dumps({"record_type": "video_result", "video_id": video.video_id,
                "predictions": [asdict(item) for item in result.predictions],
                "failures": [asdict(item) for item in result.failures]}, allow_nan=False) + "\n")
            stream.flush()
    return BatchPredictions(tuple(predictions), summary, category, combined, tuple(failures), strategy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=JSON_VALUE")
    args = parser.parse_args()
    contents = args.config.read_text(encoding="utf-8")
    if args.config.suffix.lower() == ".json":
        values = json.loads(contents)
    else:
        import yaml
        values = yaml.safe_load(contents)
    for override in args.set:
        key, separator, value = override.partition("=")
        if not separator:
            parser.error("Each override must be KEY=JSON_VALUE")
        values[key] = json.loads(value)
    cfg = ExperimentConfig.model_validate(values)
    if cfg.evaluate_summary and cfg.summary_metric_snapshot is None:
        parser.error("Summary evaluation requires a local pinned summary_metric_snapshot; smoke runs must explicitly disable it")
    if cfg.summary_metric_snapshot is not None:
        snapshot = cfg.summary_metric_snapshot.resolve()
        if not snapshot.is_dir() or len(snapshot.name) != 40 or any(c not in "0123456789abcdef" for c in snapshot.name):
            parser.error("Metric snapshot must be an existing Hugging Face commit snapshot directory")
    manifest = json.loads(cfg.manifest.read_text(encoding="utf-8"))
    by_id = {r["video_id"]: r for r in manifest["records"]}
    if any(video_id not in by_id or not by_id[video_id]["complete_record"] for video_id in cfg.video_ids):
        parser.error("Every selected video must have a complete manifest record")
    records = [by_id[video_id] for video_id in cfg.video_ids]
    errors = verify_manifest({"ground_truth": manifest["ground_truth"], "records": records}, cfg.dataset_root)
    if errors:
        raise ValueError("Input integrity failed: " + "; ".join(errors))
    import torch
    from src.config import InferenceConfig
    from src.inference_utils import create_messages, run_inference
    from src.model_utils import load_model
    from src.pipeline import prepare_videos
    from src.category_utils import is_canonical_category, normalize_category

    output = cfg.output / uuid4().hex
    output.mkdir(parents=True)
    resolved = cfg.model_dump(mode="json")
    lineage = source_lineage() | {"model_revision": cfg.model_revision, "processor_revision": cfg.model_revision,
        "manifest_hash": sha256_file(cfg.manifest), "sample_hash": canonical_hash(cfg.video_ids),
        "inference_config_hash": canonical_hash(resolved)}
    lineage["experiment_runner_hash"] = sha256_file(Path(__file__))
    lineage["video_decoder"] = "torchcodec" if os.environ.get("VIDEO_REQUIRE_TORCHCODEC") == "1" else "processor-default"
    lineage["code_hash"] = canonical_hash([lineage["code_hash"], lineage["experiment_runner_hash"]])
    runtime = InferenceConfig(video_folder=cfg.dataset_root / "videos", audio_folder=output,
        audio_transcript_folder=cfg.dataset_root / "audio_transcripts", ground_truth_file=cfg.dataset_root / manifest["ground_truth"]["path"],
        model_name=cfg.model_name, model_revision=cfg.model_revision, max_frames=cfg.max_frames,
        csv_folder=output, statistics_folder=output, file_name="experiment", use_kv_cache=True,
        inference_strategy=cfg.strategy)
    torch.cuda.reset_peak_memory_stats()
    pipe, load_seconds = load_model(runtime)
    if getattr(pipe.model.config, "_commit_hash", None) != cfg.model_revision:
        raise RuntimeError("Loaded model differs from pinned revision")
    transcripts = {r["video_id"]: cfg.dataset_root / r["transcript"]["path"] for r in records}
    paths = [cfg.dataset_root / r["video"]["path"] for r in records]
    prepared, preparation_seconds = prepare_videos(paths,
        transcript_loader=lambda video_id, _: transcripts[video_id].read_text(encoding="utf-8"),
        message_factory=create_messages)
    start = time.perf_counter()
    predictions = run_recorded_inference(prepared,
        lambda messages, mode: run_inference(pipe, messages, mode=mode,
            constrain_category=cfg.constrain_category), cfg.strategy, output / "predictions.jsonl")
    elapsed = time.perf_counter() - start
    peak_memory = torch.cuda.max_memory_allocated()
    with runtime.ground_truth_file.open(encoding="utf-8", newline="") as stream:
        truth = {row["video_id"]: row for row in csv.DictReader(stream)}
    items = predictions.predictions
    evaluated = [p for p in items if is_canonical_category(truth[p.video_id]["category"])]
    metrics = {"error_rate": len(predictions.failures) / len(paths), "peak_gpu_memory_bytes": peak_memory,
        "inference_seconds": elapsed, "model_load_seconds": load_seconds, "input_preparation_seconds": preparation_seconds}
    if evaluated:
        metrics["category_accuracy"] = sum(normalize_category(truth[p.video_id]["category"]) == p.category for p in evaluated) / len(evaluated)
    eligible_count = sum(is_canonical_category(truth[path.stem]["category"]) for path in paths)
    correct_count = sum(normalize_category(truth[p.video_id]["category"]) == p.category for p in evaluated)
    metrics["prediction_coverage"] = len(items) / len(paths)
    if eligible_count:
        metrics["category_accuracy_all_attempted"] = correct_count / eligible_count
    latencies = [sum(n or 0 for n in (p.summary_time, p.category_time, p.combined_time)) for p in items]
    if latencies:
        metrics["latency_p50_seconds"] = statistics.median(latencies)
        # Explicit nearest-rank percentile; no fabricated distribution for failed items.
        import math
        metrics["latency_p95_seconds"] = sorted(latencies)[math.ceil(.95 * len(latencies)) - 1]
    metric_hash = None
    quality_status = "incomplete"
    environment = {"gpu": torch.cuda.get_device_name(0), "torch": version("torch"), "transformers": version("transformers")}
    if os.environ.get("VIDEO_REQUIRE_TORCHCODEC") == "1":
        environment["torchcodec"] = version("torchcodec")
    # Do not keep VLM weights/allocator caches alive while loading the CPU scorer.
    del pipe
    import gc
    gc.collect()
    torch.cuda.empty_cache()
    (output / "inference.json").write_text(json.dumps({"quality_status": "incomplete",
        "metrics": metrics, "lineage": lineage, "environment": environment,
        "predictions": [asdict(p) for p in items], "failures": [asdict(f) for f in predictions.failures]},
        indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if cfg.evaluate_summary and items:
        print("Inference saved; VLM released; starting CPU BERTScore", flush=True)
        from bert_score import score
        from transformers import AutoConfig
        snapshot = cfg.summary_metric_snapshot.resolve()
        if len(snapshot.name) != 40 or any(c not in "0123456789abcdef" for c in snapshot.name):
            raise ValueError("Metric snapshot must be a Hugging Face commit snapshot directory")
        model_config = AutoConfig.from_pretrained(snapshot, local_files_only=True)
        metric_layers = cfg.summary_metric_layers or model_config.num_hidden_layers
        if metric_layers > model_config.num_hidden_layers:
            raise ValueError("Summary metric layer exceeds the scorer architecture")
        _, _, f1 = score([p.summary for p in items], [truth[p.video_id]["summary"] for p in items],
            model_type=str(snapshot), num_layers=metric_layers, device="cpu", batch_size=1, verbose=False)
        metrics["bertscore_f1"] = float(f1.mean())
        metric_hash = canonical_hash({"snapshot_revision": snapshot.name, "bert_score": version("bert-score"),
            "num_layers": metric_layers, "rescale_with_baseline": False})
        quality_status = "complete" if evaluated else "incomplete"
    report = {"schema_version": "1", "purpose": "candidate_evaluation" if cfg.evaluate_summary else "smoke",
        "name": cfg.name, "sample_count": len(paths), "category_evaluated_count": len(evaluated),
        "category_eligible_count": eligible_count, "category_correct_count": correct_count,
        "summary_evaluated_count": len(items) if cfg.evaluate_summary else 0,
        "quality_status": quality_status, "summary_metric_hash": metric_hash, "lineage": lineage,
        "environment": environment,
        "metrics": metrics, "resolved_config": resolved,
        "predictions": [asdict(p) for p in items], "failures": [asdict(f) for f in predictions.failures]}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote immutable experiment report: {output / 'report.json'}")


if __name__ == "__main__":
    main()
