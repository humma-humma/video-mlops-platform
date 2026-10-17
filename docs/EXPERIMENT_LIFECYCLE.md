# Experiments and candidate gates

`python -m scripts.run_experiment --config configs/experiments/local-smoke.json`
runs a small pinned GPU smoke. Install `requirements-experiments.txt` in a serving
GPU environment; the research `uv.lock` retains its independent Torch stack.
JSON and YAML configurations reject unknown fields and floating model revisions.
Overrides use JSON values, e.g. `--set 'max_frames=8'`. Reports use a new run
directory under `data/outputs/experiments/`, so reruns do not overwrite evidence.

Before inference, selected video/transcript checksums and ground truth must match
the manifest. `python -m scripts.verify_manifest` verifies the complete dataset.
Reports include exact model/processor revisions, source and prompt hashes, taxonomy,
manifest/sample/config hashes, runtime versions, predictions, failures, per-video
timings, and peak inference GPU memory. P95 uses nearest rank across successful
samples; failed samples contribute to error rate rather than invented durations.
Input/model preparation is reported separately from inference latency.
New reports also include prediction coverage, eligible/correct/evaluated counts,
and category accuracy across all attempted eligible inputs, counting failed
outputs as incorrect. The original category accuracy remains conditional on
successful eligible outputs. Experiment journals retain raw generations before
validation. Category-token constraints are opt-in and restricted to two-pass
experiments; canonical output does not imply a correct classification.

Summary evaluation requires `evaluate_summary: true` and an existing
`summary_metric_snapshot` directory whose name is the exact Hugging Face commit.
The evaluator runs local BERTScore on CPU, logs scorer version/layer configuration,
and hashes its metric identity. Download this snapshot before running a full
candidate experiment. The supplied smoke explicitly disables summary evaluation
and cannot pass a deployment gate. It is not the original 2.2B quality baseline.
Set `summary_metric_layers` explicitly to select a scorer layer. Newly prepared
comparisons use 17 after negative-reference controls exposed saturation at 24.
Omitting the field retains historical full-depth scoring. Changing the layer
changes the metric hash and requires a compatible new baseline.

## Reviewed thresholds

No production policy is shipped with invented thresholds. First create a
representative baseline, review its outputs and operational measurements, and
store a policy JSON containing:

- `baseline_hash`: canonical SHA-256 of the exact baseline report;
- `reviewed_by`, `minimum_samples`, `minimum_category_samples`;
- `max_bertscore_drop`, `max_accuracy_drop`, `max_error_rate`;
- `max_latency_ratio`, `max_gpu_memory_ratio`.

The `GatePolicy` schema defines bounds. Review the policy in Git. A name in a
JSON file records attribution; it does not implement an identity/approval system.
Synthetic numerical thresholds in tests are not a production policy.

```bash
python -m scripts.candidate_gate --candidate candidate.json --baseline baseline.json --policy reviewed-policy.json --output gate.json
```

The command fails for incomplete quality measurements, smoke reports, insufficient
coverage, changed baseline bytes, incompatible evaluation inputs/runtime, missing
lineage, or quality/performance regressions. It does not update the baseline.
There is no silent override.

The [local demonstration policy](../configs/gates/local-demo.json) is a
provisional, author-selected exercise against two existing **2.2B experiment**
reports. The [recorded gate](../reports/local_demo_gate.json) rejects the
fewer-frame candidate for category coverage (19 < 20), error rate (17.4% >
15%), and p95 latency (40.09 s > 1.25 × 22.16 s). The baseline hash is pinned
and the reports contain real measurements; the policy has not been independently
reviewed and does not qualify the distinct 500M serving bundle for production.
This exercise demonstrates the rejection mechanism, not a model promotion.

## MLflow

Start the local tracking profile with `docker compose --profile tracking up -d`.
The UI listens at `http://localhost:5000`; SQLite metadata and proxied artifacts
persist in the separate `mlflow_data` volume. This is a single-instance local
tracking setup. Service videos/results remain in PostgreSQL/MinIO.

```bash
python -m scripts.track_candidate --candidate candidate.json --baseline baseline.json --policy reviewed-policy.json
```

This logs candidate/baseline/policy/gate/bundle metadata, parameters, and metrics.
Failed candidates remain inspectable. Add `--register-as video-inference-bundle
--image-digest sha256:<actual-image-digest>` only for a passing candidate and a
built immutable image. Registration recomputes the gate and requires a digest;
it registers inference metadata referencing pinned weights, not a trained model.
It does not assign production aliases, verify a remote image exists, or deploy.
Staging rollout must independently verify the registry version and image digest.

The tracking integration uses the [official MLflow image](https://mlflow.org/docs/latest/ml/docker)
and [MLflow client API](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.client.html).
Live tracking/registry acceptance still requires the profile and a real quality
candidate; mocked SDK tests verify call contracts only.
