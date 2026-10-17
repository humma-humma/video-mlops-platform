# Development quality comparison — 2026-10-09

All three isolated experiments completed in suite
`2da0a29dd0ed47bcabf0017136eb55d8`. The earlier SIGKILL did not recur.
Reports record TorchCodec 0.7.0, Torch 2.8.0+cu126, Transformers 4.56.1,
and NVIDIA GeForce RTX 2080. Service readiness after the run is `ok`.

| Configuration | Valid results | Failures | Correct categories / all 23 | P95, successful results | Peak allocated GPU |
|---|---:|---:|---:|---:|---:|
| Baseline, 4 frames, two passes | 20/23 | 3/23 (13.0%) | 4/23 (17.4%) | 22.16 s | 6.34 GiB |
| 2 frames, two passes | 19/23 | 4/23 (17.4%) | 4/23 (17.4%) | 40.09 s | 6.05 GiB |
| 4 frames, combined JSON | 6/23 | 17/23 (73.9%) | 2/23 (8.7%) | 5.35 s | 6.33 GiB |

The reported category accuracies of 20.0%, 21.1%, and 33.3% use successful
outputs as their denominators. Combined generation's apparent accuracy/latency
advantage excludes 17 failed videos. It is not an acceptable optimization.
Two-frame generation reduces peak GPU allocation by about 4.5%, but adds a
failure and raises successful-output P95 by about 81% in this single run.
Neither optimization should be promoted.

All baseline/two-frame failures are out-of-taxonomy category outputs. Combined
generation fails JSON parsing for 13 videos, schema validation for three, and
taxonomy validation for one. These are model-output contract failures, rather
than recorded decoder or CUDA exceptions. The raw invalid generations were not
retained by this version, so exact malformed text cannot be diagnosed from the
saved failure messages alone.

Unrescaled, all-layer BERTScore F1 is 0.98666, 0.98714, and 0.98025 respectively.
These scores cover different successful subsets (20, 19, and 6 videos) and
cannot establish a paired quality improvement. They also require calibration
with unrelated-reference controls and factual human review before use as a
production quality gate. The development set has only one video per eligible
category and is not a representative production evaluation set.

Verification recomputed report file hashes, source/runner hashes, manifest and
sample hashes, category accuracy and failure rates; checked identical pinned
model/scorer/runtime and all 23 journal entries per experiment. Original reports
were preserved. No reviewed policy, gate pass, registry promotion, or production
quality approval was created. Container image digests are still missing from
the experiment lineage.

Machine-readable evidence is in [quality_benchmark_review.json](quality_benchmark_review.json).
The [69-row review sheet](quality_benchmark_review.csv) includes expected and
predicted summaries/categories plus failure details for every attempted video.

Next: inspect mismatched categories and factual summaries, retain raw invalid
generations in the next diagnostic run, and validate the scorer against negative
controls. Repair model-output reliability before selecting production quality
tolerances or approving an optimization. The shared loader change still needs a
rebuilt serving image and GPU smoke acceptance; restarting the old worker does
not rebuild it.
