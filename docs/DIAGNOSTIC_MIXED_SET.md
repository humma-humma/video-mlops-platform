# Retrospective mixed incident set (v1)

The [frozen case manifest](../reports/diagnostics/mixed_cases_v1.json) aggregates 12 previously labeled evidence bundles from seven source collections. It was assembled on 2026-10-19 **after** those incidents and rules existed. The manifest preserves each source label, split and origin, and names its source manifest and incident group. The [evaluation](../reports/diagnostics/mixed_evaluation_v1.json) records a SHA-256 of this manifest, every bundle hash and the diagnostic-rules hash. New incidents belong in a new manifest version rather than edits to v1.

| Source collection | Cases | Supported diagnoses | Correct abstentions |
| --- | ---: | ---: | ---: |
| Historical API jobs | 4 | 1 missing-input report | 3 |
| Live MinIO interruption | 1 | 1 artifact-check failure report | 0 |
| Damaged-video run before preflight | 2 | 0 | 2 |
| Damaged-video run after preflight | 1 | 1 decode-failure report | 0 |
| Live GPU admission burst and after-drain control | 2 | 1 capacity limit | 1 |
| Isolated HTTP rate-limit control | 1 | 0 | 1 |
| Live unrelated CPU-worker interruption | 1 | 0 | 1 |
| **Total** | **12** | **4** | **8** |

All 12 predictions match their **evidence-level** labels: 4/4 supported diagnoses and 8/8 expected abstentions. All four non-abstaining diagnoses cite paths that resolve in their bundles. There are zero wrong diagnoses, zero missed evidence-supported diagnoses and zero false-confident diagnoses on this set. The inherited source splits are 5/5 development and 7/7 held-out, but “held-out” is **not** an independent test here: the set is retrospective, the cases were already evaluated separately, and some share one experiment or known mechanism. These numbers verify the current evidence contract and abstention behavior; they do not estimate root-cause accuracy or performance on new systems. In particular, a reported failure stage does not prove its underlying cause, and the isolated 429 control is not a deployed incident.

Reproduce without Docker, a GPU, or new job submissions:

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.diagnostic_workbench evaluate `
  --cases reports/diagnostics/mixed_cases_v1.json `
  --output reports/diagnostics/mixed_evaluation_v1.json
& '.\.venv\Scripts\python.exe' -m pytest -q tests/test_diagnostic_mixed_set.py
```

The test checks that labels and splits still match the source manifests, bundle hashes match the report, and the frozen manifest and recorded rule hashes remain unchanged. Later rule or schema versions can be evaluated separately without rewriting this historical result. The v1 manifest SHA-256 is `245d546e9e7c7fe73ceb87cd0d25a6c2c7ce0504a760c8e732c961213a71ac3f`.

The next evaluation should be prospective: define labels and confounders before collecting a genuinely new incident family, then run the unchanged rules and record misses as well as abstentions. That would test generalization more meaningfully than adding related controls to this set.
