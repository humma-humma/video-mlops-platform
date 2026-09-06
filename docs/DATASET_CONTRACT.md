# Dataset and Taxonomy Contract

## Dataset version

The initial local dataset is identified as `tiktok-video-v1`. Its machine-readable manifest is stored at `data/manifests/tiktok-video-v1.json` and contains paths, byte sizes, and SHA-256 checksums for every available video and transcript.

Regenerate it from the repository root with:

```bash
python -m scripts.build_dataset_manifest
```

Current inventory:

| Item | Count |
|---|---:|
| Logical records | 277 |
| Videos | 271 |
| Transcripts | 270 |
| Ground-truth rows | 276 |
| Complete records | 270 |
| Summary-evaluable records | 270 |
| Category-evaluable records | 238 |

The manifest, rather than directory enumeration order, is the long-term source for experiment membership. The current CLI now sorts filenames to remain deterministic until manifest-driven experiments are implemented.

## Known incomplete records

- Six ground-truth IDs have no corresponding video or transcript.
- `7353311795374738721(1)` has a video but no transcript or ground truth. It appears to be a duplicate copy and is excluded by its literal ID rather than silently merged.

No source data is deleted or renamed by manifest generation.

## Category taxonomy

The canonical category taxonomy is `tiktok-video-v1`, defined in `src/taxonomy.py`. Prompt options and evaluation both import this definition so they cannot drift independently.

The following harmless label aliases are canonicalized:

| Source label | Canonical label |
|---|---|
| `Entertainment` | `Entertainment & Shows` |
| `Entertainment and Shows` | `Entertainment & Shows` |
| `Entertainment, Shows` | `Entertainment & Shows` |

Matching is case-insensitive, and a numbered model prefix or trailing period is removed.

## Noncanonical ground truth

The supplied ground truth contains labels that the model prompt does not permit:

- `News, Politics`
- `Business`

These labels are not guessed into another category. During evaluation:

- Their summaries remain part of BERTScore evaluation.
- Their rows are excluded only from category accuracy/F1.
- The excluded count and labels are emitted with the category metrics.
- Out-of-taxonomy model predictions on otherwise valid rows remain incorrect predictions; they are not excluded.

Of the 270 summary-evaluable records, 32 have a noncanonical category, leaving 238 records for a fair category evaluation. This policy changes the denominator, so new category metrics must not be compared directly with historical category metrics that scored all raw labels.

## Versioning rule

Any addition, removal, split, merge, or semantic reinterpretation of a category requires:

1. A new taxonomy version.
2. Updated prompt and evaluation tests.
3. A new dataset manifest when ground-truth labels change.
4. A new benchmark baseline; metrics across incompatible taxonomy versions must not share one gate.
