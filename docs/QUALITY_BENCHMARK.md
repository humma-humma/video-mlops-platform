# Quality comparison after local acceptance

Local service acceptance is recorded in `reports/local_acceptance.json`. The
next step is real quality measurement; repeating service smoke checks does not
provide it.

Run from the prepared Windows project PowerShell:

```powershell
& .\scripts\run_quality.ps1
```

This builds a separate benchmark image with the serving Torch/Transformers
versions, TorchCodec 0.7.0, and BERTScore. It downloads the exact public model/scorer snapshots
into `artifacts/benchmark-model-cache` and retains them for subsequent runs.
The model weights require approximately 12 GB of download/storage, plus image
and tokenizer files. No paid inference provider or cloud GPU is used.

The image build verifies that TorchCodec can load its FFmpeg libraries. Before
loading the VLM, a separate process checks bounded decoding on the selected
video with the largest estimated full-frame footprint. Look for `PASS bounded
decoder preflight` with at most four sampled frames. Sampling is explicitly
enabled; setting `num_frames` alone does not enable it in this Transformers
version. An unavailable decoder stops the run instead of falling back.

Pinned revisions:

- [SmolVLM2-2.2B-Instruct](https://huggingface.co/HuggingFaceTB/SmolVLM2-2.2B-Instruct/commit/482adb537c021c86670beed01cd58990d01e72e4):
  `482adb537c021c86670beed01cd58990d01e72e4`.
- [XLM-RoBERTa-large](https://huggingface.co/FacebookAI/xlm-roberta-large/commit/c23d21b0620b635a76227c604d44e43a9f0ee389):
  `c23d21b0620b635a76227c604d44e43a9f0ee389`.
- BERTScore 0.3.13, unrescaled F1, explicit layer 17, batch size one on CPU
  for newly prepared full comparisons. The first completed suite used layer 24;
  scorer controls exposed its weak discrimination. The layer is part of the
  metric hash, so historical layer-24 reports must not be mixed with layer 17.

The script gracefully stops a running service worker with up to 960 seconds to
finish its active job, freeing GPU memory. API/metadata/storage remain running;
readiness will report degraded while the worker is stopped. The script restores
the worker in `finally`, including after benchmark failures. If no worker was
running initially, it does not start one. Avoid submitting new service work
during this maintenance window. Normal failures preserve completed reports and
downloaded checkpoints. Closing/killing PowerShell can bypass `finally`; restart
the previous worker with `docker compose start worker` if necessary.

## Fixed development subset

`data/manifests/development-eval-v1.json` contains 23 videos, one per category
represented by complete, canonical dataset records. A SHA-256 ordering using
the fixed seed `video-mlops-eval-v1` chooses videos before predictions are seen.
Rare labels are not duplicated. Lipsync and Society have no eligible records.
The subset records the original manifest hash and sample hash.

This gives broad label coverage for development, not population-representative
accuracy or a production acceptance set. Curate a larger representative set,
review failures/hallucinations, and repeat measurements before approving quality
tolerances. A single observation per category cannot support per-category SLAs.

## Three isolated runs

1. Baseline: pinned 2.2B model, four frames, two-pass generation.
2. Frame optimization: same model/scorer/subset, two frames, two-pass generation.
3. Generation optimization: same model/scorer/subset, four frames, combined JSON.

Each run uses a fresh process and offline pinned snapshots after download.
Reports record BERTScore F1, category accuracy/coverage, failure rate, per-video
timings/predictions, nearest-rank P50/P95, and peak inference GPU memory. Model
loading and input preparation remain separate from inference latency. Each
completed video's predictions are flushed to `predictions.jsonl`. After
inference, the VLM is released and `inference.json` is saved before scoring.
BERTScore runs on CPU in batches of one; this stage can take substantial time. There is no
automatic switch to a smaller model or a different metric if resources run out.

Inspect `data/outputs/quality-suite/<run-id>/comparison.json` and its three linked
experiment reports. A failure stops the sequence without claiming completion.
Comparison completion does not approve a deployment: no thresholds, gate policy,
registry alias, or promotion are created. Use the measured baseline to review
quality examples and choose a policy as described in
[experiment lifecycle](EXPERIMENT_LIFECYCLE.md).

## Preparation checks without GPU/network

The subset selector has deterministic CPU tests. The configuration preparer can
be checked without downloading models:

```bash
python -m scripts.build_evaluation_subset
python -m scripts.prepare_quality_benchmark --skip-download
```

These commands only prepare data/configuration. They do not prove the benchmark
container, checkpoints, or quality measurements work. Container build and the
three real runs still require acceptance on the user's Docker engine.

## SIGKILL during the first baseline

The first run on 2026-10-09 downloaded both checkpoints but its baseline child
was killed with signal 9 after seven videos. The next selected input,
`7323547689201765664`, has 4,150 frames at 576 by 1,024 pixels: approximately
7.34 GB of RGB data before decoder copies. The fallback Torchvision decoder
materializes the entire video before selecting frames. This makes memory
exhaustion the leading explanation; the signal alone does not prove OOM.

The corrected image uses bounded TorchCodec decoding and explicit sampling.
Rerun the same PowerShell command above; downloaded snapshots are reused.
Each run gets a fresh directory. A killed experiment now produces
`failure.json` with cgroup memory counters; compare `oom_kill` before/after to
confirm a cgroup OOM. Partial prediction journals are evidence, not completed
quality results, and the script does not automatically resume or promote them.

The orphan-container warning comes from using a separate Compose file with the
same project name. Do not add `--remove-orphans`: those containers are the
service stack that the script restores after benchmarking.

## Investigate output reliability and scorer discrimination

The completed development comparison is reviewed in
[quality_benchmark_review.md](../reports/quality_benchmark_review.md). Its failures
require diagnosis before another full comparison or a production policy.

```powershell
& .\scripts\run_quality.ps1 -Diagnostics
```

This rebuilds the benchmark image and reuses the existing checkpoint cache. It
selects the latest completed suite, scores up to eight fixed reference summaries
against themselves, against cyclically mismatched references, and against saved
model summaries. CPU scoring runs separately for layers 24 and 17. Layer 17 is
the XLM-R-large setting in the pinned
[BERTScore 0.3.13 mapping](https://github.com/Tiiiger/bert_score/blob/v0.3.13/bert_score/utils.py).
The report records each pair, scorer identity, means, and separation between self
and mismatched scores. It does not infer production tolerances or rewrite old
scores. These controls test discrimination, not factual correctness.
Completed controls are reused when their baseline checksum and both pinned
metric identities match; the new diagnostics summary records their source.

Two GPU experiments then use the same four debug videos: up to three baseline
category failures and one successful output. One tries two-pass generation with
category-token constraints; the other retains the original combined strategy
to capture invalid JSON. There are two model loads; this can still take several
minutes. The worker is gracefully stopped/restored as with the full benchmark.

The category constraint is opt-in (`constrain_category: true`) and permits only
tokenizations of canonical labels followed by EOS, with a token budget derived
from the tokenizer. It guarantees label validity, not label accuracy. Combined
generation remains strictly validated; invalid JSON is retained for diagnosis.

Inspect `data/outputs/quality-diagnostics/<id>/diagnostics.json`,
`scorer-controls.json`, and the linked experiment `predictions.jsonl` files.
New journals contain `generation` records (raw outputs and timings) and
`video_result` records (validated predictions/failures). A raw generation is
flushed before validation, preserving malformed model text. The original
benchmark journals have only per-video result records and remain unchanged.

New reports add `prediction_coverage` and `category_accuracy_all_attempted`;
the existing `category_accuracy` still uses successful eligible outputs.
Counts explicitly identify eligible, evaluated, correct, and summary-evaluated
samples. This debug set is selected using observed failures and cannot qualify
for deployment; its experiment reports disable summary evaluation and retain
the smoke purpose. Improved accuracy still requires a new, complete comparison
and representative held-out evaluation.

The first diagnostic execution exposed a pipeline-argument bug: generation
constraints were incorrectly passed as preprocessing arguments. Generation
settings now use the pipeline's `generate_kwargs` parameter. Real pipeline and
GPU callback checks verify this boundary. See the
[diagnostic review](../reports/quality_diagnostics_review.md) for evidence and
the limitations of both the earlier tests and the quality scores.

## Full constrained two-pass comparison

The corrected 2.2B diagnostic returned four valid results out of four, with two
correct categories. Combined JSON again failed all four. This resolves the
tested category-format failures, not classification quality. Evidence is saved
in [constrained_diagnostic_acceptance.json](../reports/constrained_diagnostic_acceptance.json).
Further repetitions of the four-video diagnostic are unnecessary without new
failures or changes to the generation boundary.

```powershell
& .\scripts\run_quality.ps1 -Constrained
```

This runs two fresh, isolated experiments on all 23 fixed development videos:
four-frame constrained two-pass generation and two-frame constrained two-pass
generation. Both use layer-17 scoring and identical model/scorer/sample pins,
so the frame comparison changes only the frame budget. The rejected combined
strategy is omitted. The original default command remains available to
reproduce its three strategies. Do not combine `-Constrained` and `-Diagnostics`.

Check the new `comparison.json` and linked reports before selecting a quality
policy. Original reports and scorer identities remain unchanged. Downloaded
checkpoints are reused; new predictions require new scorer measurements.
The wrapper restores the worker on normal completion/failure. This remains a
development comparison, with representative held-out factual review and
serving-image acceptance still required before deployment.

The first full constrained comparison completed as suite
`91a00867c3314887b9b0f81b9da73a00`. Both runs returned 23/23 valid results;
four frames classified 8/23 correctly and two frames classified 5/23 correctly.
Four frames remain the development reference; the two-frame speed/memory
savings accompany an accuracy regression. See the
[verified comparison](../reports/constrained_quality_review.md) and review sheet.
Another run of the same command is unnecessary until a new hypothesis or
implementation change requires verification.

## Category review and reserved evaluation

The [case-by-case review](../reports/classification_error_review.md) covers all
15 four-frame category mismatches using supplied transcripts, references and
independently sampled frames. Seven have clear topic/purpose errors; eight
need taxonomy or provenance adjudication. Ten misses use the broad
Entertainment & Shows label. Original accuracy remains 8/23; no labels or
scores were changed. Summary issues include inverted intent, incorrect visible
text, repetition and omitted purpose; reference data also needs correction.

`data/manifests/reserved-eval-v1.json` reserves 57 examples across 21 categories
without inference. `scripts/build_reserved_evaluation.py` deterministically
excludes 24 IDs mentioned by local reports, configs and output evidence,
including configured/failed attempts. The manifest records hashes of that
exposure evidence and refuses to replace an existing differing reservation.
Preserve this version; review later exposure before using it.

This is a reserved set, not a trusted production acceptance set. Historical
research/training exposure is unknown. Independent annotation, missing-category
collection and representative sampling remain necessary. Do not tune prompts
on its examples. First adjudicate the documented taxonomy boundaries, then
test a topic/purpose classification prompt on development data only. The
proposed prompt change is unimplemented and has no measured improvement yet.
