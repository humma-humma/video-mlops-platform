import pandas as pd
from sklearn.metrics import accuracy_score, f1_score

from src.category_utils import is_canonical_category, normalize_category
from src.taxonomy import TAXONOMY_VERSION


def evaluate_with_stats(
    ground_truth: pd.DataFrame,
    test_df: pd.DataFrame,
    bertscore_fn=None,
):
    """Compute BERTScore + category metrics and save results."""
    if bertscore_fn is None:
        from bert_score import score as bertscore_fn

    refs, cands = ground_truth["summary"].tolist(), test_df["summary"].tolist()
    P, R, F1 = bertscore_fn(
        cands,
        refs,
        lang="en",
        model_type="xlm-roberta-large",
        verbose=True,
    )

    y_true_all = ground_truth["category"].map(normalize_category)
    y_pred_all = test_df["category"].map(normalize_category)
    valid_ground_truth = y_true_all.map(is_canonical_category)
    if not valid_ground_truth.any():
        raise ValueError("No ground-truth categories belong to the configured taxonomy")

    y_true = y_true_all[valid_ground_truth]
    y_pred = y_pred_all[valid_ground_truth]
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, average="weighted")
    invalid_ground_truth = sorted(y_true_all[~valid_ground_truth].unique().tolist())
    invalid_predictions = int((~y_pred.map(is_canonical_category)).sum())

    return {
        "BERTScore": {
            "Precision": {"mean": float(P.mean()), "std": float(P.std())},
            "Recall": {"mean": float(R.mean()), "std": float(R.std())},
            "F1": {"mean": float(F1.mean()), "std": float(F1.std())},
        },
        "Category": {
            "TaxonomyVersion": TAXONOMY_VERSION,
            "Accuracy": acc,
            "F1_weighted": f1,
            "EvaluatedCount": int(valid_ground_truth.sum()),
            "ExcludedGroundTruthCount": int((~valid_ground_truth).sum()),
            "ExcludedGroundTruthLabels": invalid_ground_truth,
            "InvalidPredictionCount": invalid_predictions,
        },
    }
