# Diagnostic review — 2026-10-10

Suite `76845c91141e43109dd9138775c8dbbc` completed both GPU experiments and
both scorer-control runs. Its baseline checksum, report/config/sample/source
digest consistency, manifest hash, journal coverage, category/error evidence,
and scorer means were independently checked. Original artifacts are unchanged.

| Scorer layer | Self references | Mismatched references | Saved model summaries |
|---|---:|---:|---:|
| 24 | 1.00000 | 0.98264 | 0.98599 |
| 17 | 1.00000 | 0.85553 | 0.87599 |

Layer 24 gives almost the same score to unrelated references and model outputs.
The earlier F1 near 0.99 is not evidence of factual summary quality. Layer 17
separates these controls more clearly, but its model-minus-mismatch mean is only
0.02046 on this small sample. Human factual review and representative held-out
evaluation remain necessary; no numerical production threshold is approved.
Newly prepared full comparison configs explicitly select layer 17 and therefore
have a different metric identity. Historical reports retain their original
24-layer identity; configs omitting `summary_metric_layers` retain historical
full-depth behavior.

The constrained-category diagnostic returned only one valid/correct result out
of four. Three raw categories were truncated to `3. Music, Singing, &`. The
combined diagnostic failed all four videos: its raw outputs were category
labels, including `Sports` and `Dance`, rather than JSON objects.

The category constraint did not actually reach generation. In Transformers
4.56.1, `ImageTextToTextPipeline._sanitize_parameters` treats unrecognized
top-level arguments as preprocessing options. Our top-level
`prefix_allowed_tokens_fn`, `num_beams`, and `do_sample` therefore did not reach
`model.generate`. The prior fake-pipeline test accepted arbitrary keywords, and
the direct tiny-model test bypassed this pipeline boundary. The prior native
GPU smoke established only that its output happened to be canonical.

The inference call now passes generation settings inside `generate_kwargs`.
A regression test exercises the real installed pipeline parameter sanitizer.
A real native 500M GPU-model check observed three prefix-callback invocations,
an explicit deterministic setting, and a canonical category. See
[pipeline_generation_verification.json](pipeline_generation_verification.json).
That single label was still incorrect for ground truth; label validity and
classification accuracy remain separate requirements. It used the native
Torchvision fallback on one small video, not the Docker bounded decoder.

Validation: 126 CPU tests passed, one Transformers-dependent test skipped in
that lightweight environment; all four decoding tests passed in the native
Transformers environment. Python compilation, Compose configuration and Git
whitespace checks passed. No candidate was promoted.

Rerun `scripts/run_quality.ps1 -Diagnostics` to verify the fixed boundary with
the pinned 2.2B Docker model. The script now reuses completed scorer controls
only when the baseline checksum, both layer identities, metric revision,
BERTScore version and rescaling configuration match. It preserves their bytes
and records the source path, avoiding another CPU calibration run. The four
failure-selected examples remain diagnostics rather than production acceptance.

Machine-readable checks and raw-output excerpts are recorded in
[quality_diagnostics_review.json](quality_diagnostics_review.json).
