"""Calibrate the scorer and investigate failed outputs using cached checkpoints."""
import argparse
import csv
from importlib.metadata import version
import json
import os
from pathlib import Path
import statistics
import shutil
import subprocess
import sys
from uuid import uuid4

from scripts.prepare_quality_benchmark import METRIC, METRIC_REVISION
from src.experiments import ExperimentConfig
from src.lineage import canonical_hash, sha256_file, verify_manifest


def control_pairs(video_ids, truth, predictions):
    """Pair the same references with self, cyclic mismatches and model outputs."""
    ids = sorted(video_ids)[:8]
    if len(ids) < 2 or len({truth[key]["summary"] for key in ids}) != len(ids):
        raise ValueError("Controls require at least two distinct reference summaries")
    pairs = []
    for index, video_id in enumerate(ids):
        reference = truth[video_id]["summary"]
        other_id = ids[(index + 1) % len(ids)]
        pairs.extend([
            {"kind": "self", "video_id": video_id, "reference_video_id": video_id,
             "candidate": reference, "reference": reference},
            {"kind": "mismatched", "video_id": video_id, "reference_video_id": other_id,
             "candidate": reference, "reference": truth[other_id]["summary"]},
        ])
        if video_id in predictions:
            pairs.append({"kind": "model", "video_id": video_id, "reference_video_id": video_id,
                          "candidate": predictions[video_id]["summary"], "reference": reference})
    return pairs


def calibration(baseline_path: Path, output: Path):
    """Use CPU only. Never rewrite the original metric or approve a quality gate."""
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    cfg = ExperimentConfig.model_validate(baseline["resolved_config"])
    manifest = json.loads(cfg.manifest.read_text(encoding="utf-8"))
    if sha256_file(cfg.manifest) != baseline["lineage"]["manifest_hash"]:
        raise ValueError("Baseline manifest changed")
    errors = verify_manifest({"ground_truth": manifest["ground_truth"], "records": []}, cfg.dataset_root)
    if errors:
        raise ValueError("Ground truth integrity failed: " + "; ".join(errors))
    truth_path = cfg.dataset_root / manifest["ground_truth"]["path"]
    with truth_path.open(encoding="utf-8", newline="") as stream:
        truth = {row["video_id"]: row for row in csv.DictReader(stream)}
    predictions = {p["video_id"]: p for p in baseline["predictions"]}
    pairs = control_pairs(cfg.video_ids, truth, predictions)
    cache = Path(os.environ.get("HF_HUB_CACHE", "artifacts/benchmark-model-cache")).resolve()
    snapshot = cache / ("models--" + METRIC.replace("/", "--")) / "snapshots" / METRIC_REVISION
    if not snapshot.is_dir():
        raise ValueError("Pinned scorer snapshot is not cached; run checkpoint preparation first")
    from bert_score import BERTScorer
    from transformers import AutoConfig
    config = AutoConfig.from_pretrained(snapshot, local_files_only=True)
    if config.num_hidden_layers != 24 or config.model_type != "xlm-roberta":
        raise ValueError("Unexpected scorer architecture")
    report = {"purpose": "metric calibration; not production quality approval",
        "baseline": str(baseline_path), "baseline_sha256": sha256_file(baseline_path),
        "script_sha256": sha256_file(Path(__file__)), "layers": [],
        "note": "Self versus mismatched references tests discrimination, not factual correctness. No acceptance threshold is inferred."}
    for layer in (24, 17):
        print(f"CPU scorer controls: layer {layer}, {len(pairs)} pairs", flush=True)
        scorer = BERTScorer(model_type=str(snapshot), num_layers=layer, device="cpu",
                            batch_size=1, rescale_with_baseline=False, idf=False)
        _, _, f1 = scorer.score([p["candidate"] for p in pairs], [p["reference"] for p in pairs])
        values = f1.tolist()
        measured = [pair | {"f1": value} for pair, value in zip(pairs, values, strict=True)]
        means = {kind: statistics.fmean(row["f1"] for row in measured if row["kind"] == kind)
                 for kind in {row["kind"] for row in measured}}
        identity = {"snapshot_revision": METRIC_REVISION, "bert_score": version("bert-score"),
                    "num_layers": layer, "rescale_with_baseline": False}
        report["layers"].append({"metric": identity, "metric_hash": canonical_hash(identity),
            "runtime": {"torch": version("torch"), "transformers": version("transformers")},
            "means": means, "self_minus_mismatched": means["self"] - means["mismatched"], "pairs": measured})
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        del scorer, f1
        import gc
        gc.collect()
    print(f"Saved scorer controls: {output}", flush=True)


def diagnostic_configs(baseline, output: Path):
    """Failure-selected debug set; explicitly unsuitable for promotion."""
    cfg = ExperimentConfig.model_validate(baseline["resolved_config"])
    failed = sorted({f["video_id"] for f in baseline["failures"]})[:3]
    succeeded = sorted(p["video_id"] for p in baseline["predictions"])
    if not failed or not succeeded:
        raise ValueError("Diagnostics require failed and successful baseline examples")
    ids = sorted(set(failed + succeeded[:1]))
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, strategy, constraint in (("constrained-category", "per_video_two_pass", True),
                                       ("combined-raw", "per_video_combined", False)):
        values = cfg.model_dump() | {"name": f"diagnostic-{name}", "video_ids": ids,
            "strategy": strategy, "constrain_category": constraint, "evaluate_summary": False,
            "summary_metric_snapshot": None, "output": output.parent / name}
        resolved = ExperimentConfig.model_validate(values)
        path = output / f"{name}.json"
        path.write_text(resolved.model_dump_json(indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def reusable_controls(baseline_path: Path, root: Path):
    """Reuse completed controls only for the same baseline and pinned metric."""
    baseline_hash = sha256_file(baseline_path)
    for path in sorted(root.glob("*/scorer-controls.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        report = json.loads(path.read_text(encoding="utf-8"))
        layers = report.get("layers", [])
        if report.get("baseline_sha256") != baseline_hash or len(layers) != 2:
            continue
        identities = [item["metric"] for item in layers]
        if {item["num_layers"] for item in identities} != {24, 17}:
            continue
        if all(item["snapshot_revision"] == METRIC_REVISION and item["bert_score"] == version("bert-score")
               and item["rescale_with_baseline"] is False for item in identities):
            return path
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path)
    parser.add_argument("--calibrate", type=Path, help="Internal CPU-only subprocess: baseline report")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.calibrate:
        if args.output is None:
            parser.error("--calibrate requires --output")
        calibration(args.calibrate, args.output)
        return
    if args.suite is None:
        completed = list(Path("data/outputs/quality-suite").glob("*/comparison.json"))
        if not completed:
            parser.error("No completed quality suite exists")
        suite = max(completed, key=lambda path: path.stat().st_mtime).parent
    else:
        suite = args.suite
    comparison = json.loads((suite / "comparison.json").read_text(encoding="utf-8"))
    baseline_path = Path(next(item["report"] for item in comparison["reports"] if item["name"].endswith("-baseline")))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    output = Path("data/outputs/quality-diagnostics") / uuid4().hex
    configs = diagnostic_configs(baseline, output / "configs")
    environment = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    # Scorer imports and allocations disappear before either VLM process starts.
    controls_source = reusable_controls(baseline_path, output.parent)
    if controls_source:
        shutil.copyfile(controls_source, output / "scorer-controls.json")
        print(f"Reusing verified scorer identity/baseline controls: {controls_source}", flush=True)
    else:
        subprocess.run([sys.executable, "-m", "scripts.quality_diagnostics", "--calibrate", str(baseline_path),
                        "--output", str(output / "scorer-controls.json")], check=True, env=environment)
    reports = []
    for path in configs:
        subprocess.run([sys.executable, "-m", "scripts.run_experiment", "--config", str(path)], check=True, env=environment)
        paths = list((output / path.stem).glob("*/report.json"))
        if len(paths) != 1:
            raise RuntimeError("Expected one diagnostic report")
        report = json.loads(paths[0].read_text(encoding="utf-8"))
        reports.append({"report": str(paths[0]), "metrics": report["metrics"], "failures": report["failures"]})
    (output / "diagnostics.json").write_text(json.dumps({"purpose": "failure-selected diagnostics, not acceptance",
        "baseline": str(baseline_path), "baseline_sha256": sha256_file(baseline_path),
        "scorer_controls": str(output / "scorer-controls.json"),
        "scorer_controls_reused_from": str(controls_source) if controls_source else None,
        "reports": reports, "promoted": False}, indent=2) + "\n", encoding="utf-8")
    print(f"PASS diagnostics execution: {output / 'diagnostics.json'}", flush=True)


if __name__ == "__main__":
    main()
