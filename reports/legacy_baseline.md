# Legacy Baseline Reference

This reference preserves the first comparison point without restoring generated output files that are deleted in the current working tree.

## Provenance

- Git commit: `2392cc4ec6652ac43eb04f49d20b4cc75b1bc2d8`
- Historical artifact: `data/outputs/statistics/smol_vlm_2.2b_pipeline_stats.json`
- Model: `HuggingFaceTB/SmolVLM2-2.2B-Instruct`
- Exact model/processor revision: not recorded by the historical run
- Dataset manifest: not recorded by the historical run
- Prompt/taxonomy version: not recorded by the historical run

## Recorded metrics

| Metric | Value |
|---|---:|
| Model load time | 7.0618 s |
| Total time | 12,219.2462 s |
| Mean summary inference | 42.4949 s |
| Mean category inference | 2.7299 s |
| BERTScore precision | 0.884679 |
| BERTScore recall | 0.861534 |
| BERTScore F1 | 0.872814 |
| Category accuracy | 0.248148 |
| Category weighted F1 | 0.253114 |

## Limitations

- The historical category metric included noncanonical ground-truth labels and is not directly comparable with taxonomy-aware category evaluation.
- The recorded inference `min`, `max`, and `std` values were placeholders, not per-video measurements.
- The run did not record a video count, exact Hugging Face revision, dataset checksum, GPU identity, or container/environment digest.
- Total time includes work that was not fully decomposed into stages.

This artifact is therefore a **legacy reference**, not the production evaluation gate. A new baseline must be generated after the stabilized pipeline records complete lineage and real latency distributions.
