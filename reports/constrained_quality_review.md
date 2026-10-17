# Constrained development comparison — 2026-10-10

Suite `91a00867c3314887b9b0f81b9da73a00` completed both 23-video runs.
All 46 attempted videos produced validated summaries and canonical categories;
neither run recorded a failure. Local service readiness after the run is `ok`.

| Configuration | Correct categories | Valid results | P95 inference | Peak allocated GPU | Layer-17 BERTScore F1 |
|---|---:|---:|---:|---:|---:|
| Four frames, constrained two-pass | 8/23 (34.8%) | 23/23 | 10.35 s | 6.34 GiB | 0.87999 |
| Two frames, constrained two-pass | 5/23 (21.7%) | 23/23 | 9.25 s | 6.05 GiB | 0.88360 |

Two frames reduce successful-output P95 by 10.6%, peak allocated GPU memory by
4.5%, and total inference elapsed time by 12.7% in this single comparison.
They lose three net correct categories: four examples change from correct to
incorrect, one changes from incorrect to correct, four are correct in both,
and fourteen are incorrect in both. The accuracy difference is -13.04
percentage points. The small summary-similarity increase of 0.00361 does not
demonstrate better factual summaries.

Keep four frames as the **development reference**. Do not promote the two-frame
optimization or treat either run as production quality acceptance. The fixed
set has one video per eligible category and is not representative held-out
evaluation. Category accuracy remains weak; label validity is now reliable on
this set, but enforcing the taxonomy does not fix semantic classification.
Combined JSON remains rejected based on the earlier diagnostics.

Verification independently checked source/runner/config/sample/manifest hashes,
selected input checksums, identical pinned model/scorer/runtime, full journal
coverage, category counts and latency percentiles. The BERTScore aggregate was
recorded from each report rather than recomputed independently. Both reports
use layer 17 and the same metric hash. They must not be mixed with the original
layer-24 scores. No original reports were overwritten and no gate policy,
production approval, registry alias or deployment was created.

Machine-readable evidence, file hashes and paired example IDs are saved in
[constrained_quality_review.json](constrained_quality_review.json). The
[46-row review sheet](constrained_quality_review.csv) includes reference and
predicted summaries/categories for every video in both runs.

The next quality work is to review the mismatched categories, taxonomy ambiguity
and summary factuality, then curate representative held-out acceptance examples.
Repeating the same benchmark without a hypothesis or implementation change adds
little evidence. Production tolerances cannot be justified by this run alone.
Live MLflow acceptance, reproducible dependency locks, CI execution, rebuilt
serving-image acceptance and cloud delivery remain separate unfinished work.
